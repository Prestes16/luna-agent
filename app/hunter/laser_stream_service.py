"""
Helius LaserStream Service
===========================
Consumidor de eventos on-chain em tempo real via Helius LaserStream WebSocket.

LaserStream é a API de streaming de alta performance da Helius:
  wss://atlas-mainnet.helius-rpc.com/?api-key=<HELIUS_RPC_KEY>

Protocolo:
  1. Conectar ao endpoint WebSocket
  2. Enviar subscription request (filtros por programa/tipo)
  3. Receber eventos: confirmed transactions, account updates, logs
  4. Filtrar InstructionError → enfileirar para análise da Hunter Engine

Referência: https://docs.helius.dev/streaming-api/laserstream
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("luna.laser_stream")

# ─── Tipos de evento ──────────────────────────────────────────────────────────

class EventType(str, Enum):
    INSTRUCTION_ERROR = "instruction_error"    # Falha de execução — possível bug explorável
    SUSPICIOUS_ACCOUNT = "suspicious_account"  # Movimento anômalo de fundos
    HIGH_VALUE_TX = "high_value_tx"            # Transação de alto valor (> threshold)
    PROGRAM_DEPLOY = "program_deploy"          # Deploy ou upgrade de programa
    UNKNOWN = "unknown"


@dataclass
class StreamEvent:
    """Evento normalizado do LaserStream."""
    event_type:      EventType
    signature:       str
    slot:            int
    block_time:      Optional[int]
    program_ids:     list[str]          # Programas envolvidos
    error_type:      Optional[str]      # Ex: "InstructionError", "InsufficientFunds"
    error_detail:    Optional[str]      # Instrução específica que falhou
    log_messages:    list[str]          # Logs da transação
    accounts:        list[str]          # Contas envolvidas
    sol_change:      float              # Variação de SOL na transação
    raw:             dict = field(default_factory=dict, repr=False)
    received_at:     float = field(default_factory=time.time)

    @property
    def is_exploitable_candidate(self) -> bool:
        """Heurística: transação que pode indicar bug explorável."""
        if self.event_type != EventType.INSTRUCTION_ERROR:
            return False
        # Filtrar erros comuns não-interessantes
        boring = {
            "InsufficientFunds", "AccountNotRent",
            "InvalidAccountData", "AccountAlreadyInitialized",
        }
        if self.error_type in boring:
            return False
        # Erros que frequentemente indicam lógica explorável
        interesting = {
            "Custom", "PrivilegeEscalation", "InvalidInstructionData",
            "InvalidArgument", "AccountDataTooSmall", "InvalidRealloc",
        }
        if self.error_type in interesting:
            return True
        # Logs contendo padrões suspeitos
        suspicious_log_patterns = [
            r"panicked", r"overflow", r"underflow", r"attempt to",
            r"constraint.*violated", r"seeds.*constraint", r"unauthorized",
            r"access.*denied", r"invalid.*signer", r"bump.*mismatch",
        ]
        all_logs = " ".join(self.log_messages).lower()
        return any(re.search(p, all_logs) for p in suspicious_log_patterns)


# ─── IDL Decoder ─────────────────────────────────────────────────────────────

class IDLDecoder:
    """
    Decodifica dados de instrução Anchor a partir de IDL local ou fetch on-chain.
    """

    def __init__(self, idl_cache_dir: Optional[str] = None) -> None:
        self._cache_dir = idl_cache_dir or os.getenv("LUNA_IDL_CACHE", "data/idl_cache")
        self._idl_map: dict[str, dict] = {}

    def load_idl(self, program_id: str, idl_path: Optional[str] = None) -> bool:
        """Carrega IDL de arquivo local ou tenta encontrar no cache."""
        if program_id in self._idl_map:
            return True

        if idl_path:
            try:
                with open(idl_path, "r", encoding="utf-8") as f:
                    self._idl_map[program_id] = json.load(f)
                    return True
            except Exception as e:
                logger.warning(f"[idl] Erro ao carregar IDL de {idl_path}: {e}")
                return False

        # Tentar carregar do cache local
        cache_path = f"{self._cache_dir}/{program_id}.json"
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    self._idl_map[program_id] = json.load(f)
                    return True
            except Exception:
                pass

        return False

    def decode_instruction(
        self,
        program_id: str,
        data_b64: str,
    ) -> Optional[dict]:
        """
        Decodifica dados de instrução usando o IDL do programa.
        Retorna dict com {name, args} ou None se não conseguir decodificar.
        """
        if program_id not in self._idl_map:
            return None

        idl = self._idl_map[program_id]
        try:
            import base64
            import struct

            data = base64.b64decode(data_b64)
            if len(data) < 8:
                return None

            # Anchor discriminator — primeiros 8 bytes identificam a instrução
            discriminator = data[:8]
            disc_hex = discriminator.hex()

            for ix in idl.get("instructions", []):
                # Anchor calcula discriminator como sha256("global:<name>")[:8]
                import hashlib
                name = ix["name"]
                disc_expected = hashlib.sha256(f"global:{name}".encode()).digest()[:8]
                if disc_expected == discriminator:
                    return {"instruction": name, "discriminator": disc_hex}

        except Exception as e:
            logger.debug(f"[idl] Falha ao decodificar instrução de {program_id}: {e}")

        return None


# ─── LaserStream Client ───────────────────────────────────────────────────────

class LaserStreamClient:
    """
    Cliente WebSocket para Helius LaserStream.

    Uso básico:
        client = LaserStreamClient()
        client.add_handler(my_event_handler)
        asyncio.run(client.start(program_ids=["MY_PROGRAM_ID"]))

    Uso com fila:
        client = LaserStreamClient()
        queue = asyncio.Queue()
        client.add_queue(queue)
        asyncio.run(client.start())
        event = await queue.get()
    """

    # Endpoint do LaserStream (Atlas — maior throughput)
    _WS_URL_TEMPLATE = "wss://atlas-mainnet.helius-rpc.com/?api-key={api_key}"
    _WS_DEVNET_TEMPLATE = "wss://atlas-devnet.helius-rpc.com/?api-key={api_key}"

    def __init__(
        self,
        api_key: Optional[str] = None,
        devnet: bool = False,
        reconnect_delay: float = 5.0,
        max_queue_size: int = 1000,
    ) -> None:
        self._api_key = api_key or os.getenv("HELIUS_RPC_KEY", "")
        self._devnet = devnet
        self._reconnect_delay = reconnect_delay
        self._max_queue_size = max_queue_size
        self._handlers: list[Callable[[StreamEvent], None]] = []
        self._queues: list[asyncio.Queue] = []
        self._running = False
        self._stats = {
            "total_events": 0,
            "instruction_errors": 0,
            "exploitable_candidates": 0,
            "connected_at": None,
            "last_event_at": None,
        }
        self._idl_decoder = IDLDecoder()

        if not self._api_key:
            logger.warning(
                "[laser] HELIUS_RPC_KEY não configurada. "
                "Defina a variável de ambiente para usar o LaserStream."
            )

    def add_handler(self, handler: Callable[[StreamEvent], None]) -> None:
        """Registra callback para cada evento recebido."""
        self._handlers.append(handler)

    def add_queue(self, queue: asyncio.Queue) -> None:
        """Enfileira eventos para processamento assíncrono externo."""
        self._queues.append(queue)

    def load_program_idl(self, program_id: str, idl_path: Optional[str] = None) -> bool:
        """Carrega IDL para decodificação de instruções."""
        return self._idl_decoder.load_idl(program_id, idl_path)

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def _ws_url(self) -> str:
        tmpl = self._WS_DEVNET_TEMPLATE if self._devnet else self._WS_URL_TEMPLATE
        return tmpl.format(api_key=self._api_key)

    def _build_subscription(self, program_ids: Optional[list[str]] = None) -> dict:
        """
        Monta o payload de subscrição do LaserStream.
        Filtra por programa quando fornecido.
        """
        params: dict = {
            "commitment": "confirmed",
            "encoding": "base64",
            "transactionDetails": "full",
            "showRewards": False,
            "maxSupportedTransactionVersion": 0,
        }

        # Filtro por programa — só recebe TXs que interagem com o programa
        if program_ids:
            params["mentions"] = program_ids

        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": ["all", params],
        }

    def _parse_event(self, raw: dict) -> Optional[StreamEvent]:
        """Converte payload bruto LaserStream → StreamEvent normalizado."""
        try:
            # Notificação de log
            params = raw.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})

            signature = value.get("signature", "")
            logs = value.get("logs", [])
            err = value.get("err")

            if not signature:
                return None

            # Determinar tipo de evento
            event_type = EventType.UNKNOWN
            error_type = None
            error_detail = None

            if err:
                event_type = EventType.INSTRUCTION_ERROR
                if isinstance(err, dict):
                    ix_err = err.get("InstructionError", [])
                    if ix_err and len(ix_err) >= 2:
                        error_detail = f"Instruction {ix_err[0]}"
                        inner_err = ix_err[1]
                        if isinstance(inner_err, dict):
                            error_type = list(inner_err.keys())[0] if inner_err else "Unknown"
                        else:
                            error_type = str(inner_err)
                    else:
                        error_type = list(err.keys())[0] if err else "Unknown"
                else:
                    error_type = str(err)

            # Extrair program IDs dos logs
            program_ids = []
            for log in logs:
                m = re.match(r"Program (\w+) (invoke|log|success|failed)", log)
                if m:
                    pid = m.group(1)
                    if pid not in program_ids:
                        program_ids.append(pid)

            return StreamEvent(
                event_type=event_type,
                signature=signature,
                slot=result.get("context", {}).get("slot", 0),
                block_time=None,
                program_ids=program_ids,
                error_type=error_type,
                error_detail=error_detail,
                log_messages=logs,
                accounts=[],     # preenchido em parse_full se necessário
                sol_change=0.0,
                raw=raw,
            )
        except Exception as e:
            logger.debug(f"[laser] Erro ao parsear evento: {e}")
            return None

    async def _dispatch(self, event: StreamEvent) -> None:
        """Despacha evento para handlers e filas registradas."""
        self._stats["total_events"] += 1
        self._stats["last_event_at"] = time.time()

        if event.event_type == EventType.INSTRUCTION_ERROR:
            self._stats["instruction_errors"] += 1
        if event.is_exploitable_candidate:
            self._stats["exploitable_candidates"] += 1
            logger.info(
                f"[laser] 🎯 CANDIDATO EXPLORÁVEL: {event.signature[:16]}...  "
                f"err={event.error_type}  programs={event.program_ids}"
            )

        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.warning(f"[laser] Erro no handler: {e}")

        for q in self._queues:
            try:
                if q.qsize() < self._max_queue_size:
                    await q.put(event)
            except Exception:
                pass

    async def start(
        self,
        program_ids: Optional[list[str]] = None,
        filter_exploitable_only: bool = False,
    ) -> None:
        """
        Inicia o loop de conexão/reconexão ao LaserStream.

        Args:
            program_ids: Filtrar apenas transações que envolvem esses programas.
            filter_exploitable_only: Se True, só despacha candidatos exploráveis.
        """
        if not self._api_key:
            raise ValueError(
                "HELIUS_RPC_KEY não configurada. "
                "Defina a variável de ambiente: export HELIUS_RPC_KEY=<sua-chave>"
            )

        self._running = True
        subscription = self._build_subscription(program_ids)

        logger.info(f"[laser] Iniciando LaserStream — {'devnet' if self._devnet else 'mainnet'}")

        while self._running:
            try:
                await self._connect_and_stream(
                    subscription, filter_exploitable_only
                )
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    f"[laser] Conexão encerrada: {e}. "
                    f"Reconectando em {self._reconnect_delay}s..."
                )
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_and_stream(
        self,
        subscription: dict,
        filter_exploitable_only: bool,
    ) -> None:
        """Loop interno de uma única sessão WebSocket."""
        try:
            import websockets  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "websockets não instalado. Execute: pip install websockets"
            )

        url = self._ws_url()
        logger.info(f"[laser] Conectando a {url[:60]}...")

        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
        ) as ws:
            self._stats["connected_at"] = time.time()
            logger.info("[laser] ✓ Conectado ao Helius LaserStream")

            await ws.send(json.dumps(subscription))

            # Aguardar confirmação de subscrição
            raw_sub = await asyncio.wait_for(ws.recv(), timeout=10)
            sub_resp = json.loads(raw_sub)
            if "error" in sub_resp:
                raise RuntimeError(f"[laser] Erro na subscrição: {sub_resp['error']}")
            logger.info(f"[laser] Subscrição confirmada: {sub_resp}")

            # Loop de recebimento
            async for raw_msg in ws:
                if not self._running:
                    break

                try:
                    data = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                # Ignorar mensagens que não são notificações de log
                if data.get("method") != "logsNotification":
                    continue

                event = self._parse_event(data)
                if event is None:
                    continue

                if filter_exploitable_only and not event.is_exploitable_candidate:
                    continue

                await self._dispatch(event)

    def stop(self) -> None:
        self._running = False
        logger.info("[laser] LaserStream parado.")


# ─── Analisador de Transações ─────────────────────────────────────────────────

class TxAnalyzer:
    """
    Analisa uma assinatura de transação específica via RPC Helius.

    Usado no comando /hunt <tx_signature> para análise forense de uma
    transação específica (não necessariamente on-chain live).
    """

    def __init__(self, rpc_url: Optional[str] = None) -> None:
        api_key = os.getenv("HELIUS_RPC_KEY", "")
        default_url = (
            os.getenv("SOLANA_RPC_URL")
            or (f"https://mainnet.helius-rpc.com/?api-key={api_key}" if api_key else None)
            or "https://api.mainnet-beta.solana.com"
        )
        self._rpc_url       = rpc_url or default_url
        # REST API endpoints (Enhanced Transaction format)
        self._tx_url        = os.getenv("HELIUS_TX_URL", f"https://api-mainnet.helius-rpc.com/v0/transactions/?api-key={api_key}")
        self._addr_tx_url   = os.getenv("HELIUS_ADDR_TX_URL", f"https://api-mainnet.helius-rpc.com/v0/addresses/{{address}}/transactions/?api-key={api_key}")
        self._idl_decoder   = IDLDecoder()

    async def fetch_transaction(self, signature: str) -> Optional[dict]:
        """Busca detalhes completos de uma transação via RPC."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx não instalado. Execute: pip install httpx")

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self._rpc_url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if "error" in result:
                raise RuntimeError(f"RPC error: {result['error']}")
            return result.get("result")

    async def analyze(self, signature: str) -> dict:
        """
        Análise completa de uma transação.
        Retorna estrutura com: status, error, programs, logs, accounts, sol_flow.
        """
        tx = await self.fetch_transaction(signature)
        if not tx:
            return {"error": "Transação não encontrada", "signature": signature}

        meta = tx.get("meta", {}) or {}
        message = tx.get("transaction", {}).get("message", {})

        # Status
        err = meta.get("err")
        status = "failed" if err else "success"

        # Programs envolvidos
        account_keys = message.get("accountKeys", [])
        programs = [
            ak["pubkey"] if isinstance(ak, dict) else str(ak)
            for ak in account_keys
            if (isinstance(ak, dict) and ak.get("signer") is False)
               or isinstance(ak, str)
        ]

        # SOL flow
        pre_balances  = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])
        sol_changes = []
        for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
            delta = (post - pre) / 1e9  # lamports → SOL
            if abs(delta) > 0.001:  # filtrar ruído
                key = account_keys[i] if i < len(account_keys) else f"account_{i}"
                pub = key.get("pubkey", str(key)) if isinstance(key, dict) else str(key)
                sol_changes.append({"account": pub, "delta_sol": round(delta, 6)})

        # Logs
        logs = meta.get("logMessages", [])

        # Detectar error type
        error_type = None
        error_detail = None
        if err and isinstance(err, dict):
            ix_err = err.get("InstructionError", [])
            if ix_err and len(ix_err) >= 2:
                error_detail = f"Instruction index {ix_err[0]}"
                inner = ix_err[1]
                error_type = list(inner.keys())[0] if isinstance(inner, dict) else str(inner)

        # Extrair programas únicos dos logs
        program_ids: list[str] = []
        for log in logs:
            m = re.match(r"Program (\w{32,}) invoke", log)
            if m and m.group(1) not in program_ids:
                program_ids.append(m.group(1))

        # Heurística: é candidato explorável?
        exploitable = bool(err) and error_type not in {
            "InsufficientFunds", "AccountNotRent",
            "AccountAlreadyInitialized", "InvalidAccountData",
        }
        panic_in_logs = any(
            re.search(r"panick|overflow|underflow|constraint.*violat|seeds.*constraint", log.lower())
            for log in logs
        )

        return {
            "signature": signature,
            "status": status,
            "error": err,
            "error_type": error_type,
            "error_detail": error_detail,
            "program_ids": program_ids,
            "log_messages": logs,
            "sol_changes": sol_changes,
            "exploitable_candidate": exploitable or panic_in_logs,
            "slot": tx.get("slot"),
            "block_time": tx.get("blockTime"),
            "fee_lamports": meta.get("fee", 0),
        }
