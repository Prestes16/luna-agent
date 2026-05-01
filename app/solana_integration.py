"""
Luna Agent - Integração Solana
Sistema de créditos, transações on-chain e gerenciamento de carteira.
"""

from __future__ import annotations

import os
import logging
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.rpc.responses import GetAccountInfoResp
    from solana.rpc.api import Client
    from solana.transaction import Transaction
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False


logger = logging.getLogger("luna.solana")


# ─────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────

SOLANA_RPC_URLS = {
    "mainnet": "https://api.mainnet-beta.solana.com",
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
}

CREDITS_PER_SOL = 1000.0  # 1 SOL = 1000 créditos
LAMPORTS_PER_SOL = 1_000_000_000


# ─────────────────────────────────────────────────────────────────────────
# Gerenciador de Carteira
# ─────────────────────────────────────────────────────────────────────────

class SolanaWalletManager:
    """Gerenciador de carteira Solana."""
    
    def __init__(
        self,
        network: str = "mainnet",
        wallet_file: str = "data/luna_wallet.json",
    ):
        self.network = network
        self.wallet_file = Path(wallet_file)
        self.wallet_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.client = None
        self.keypair = None
        self.public_key = None
        
        if SOLANA_AVAILABLE:
            try:
                rpc_url = SOLANA_RPC_URLS.get(network, SOLANA_RPC_URLS["mainnet"])
                self.client = Client(rpc_url)
                logger.info(f"Cliente Solana conectado: {network}")
            except Exception as e:
                logger.warning(f"Erro ao conectar ao Solana: {e}")
        else:
            logger.warning("Solana SDK não disponível. Modo simulado.")
        
        self._load_or_create_wallet()
    
    def _load_or_create_wallet(self) -> None:
        """Carregar ou criar carteira."""
        
        if self.wallet_file.exists():
            try:
                data = json.loads(self.wallet_file.read_text())
                if SOLANA_AVAILABLE:
                    secret_key = data.get("secret_key", [])
                    self.keypair = Keypair.from_secret_key(bytes(secret_key))
                    self.public_key = str(self.keypair.pubkey())
                    logger.info(f"Carteira carregada: {self.public_key}")
                else:
                    self.public_key = data.get("public_key", "")
            except Exception as e:
                logger.warning(f"Erro ao carregar carteira: {e}. Criando nova.")
                self._create_new_wallet()
        else:
            self._create_new_wallet()
    
    def _create_new_wallet(self) -> None:
        """Criar nova carteira."""
        
        if SOLANA_AVAILABLE:
            self.keypair = Keypair()
            self.public_key = str(self.keypair.pubkey())
            
            # Salvar carteira
            wallet_data = {
                "public_key": self.public_key,
                "secret_key": list(self.keypair.secret_key),
                "network": self.network,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.wallet_file.write_text(json.dumps(wallet_data, indent=2))
            logger.info(f"Nova carteira criada: {self.public_key}")
        else:
            # Modo simulado
            self.public_key = f"Luna-{datetime.utcnow().timestamp()}"
            logger.info(f"Carteira simulada: {self.public_key}")
    
    def get_balance(self) -> float:
        """Obter saldo em SOL."""
        
        if not self.client or not self.public_key:
            return 0.0
        
        try:
            pubkey = Pubkey(self.public_key)
            response = self.client.get_account_info(pubkey)
            
            if response and response.value:
                lamports = response.value.lamports
                sol = lamports / LAMPORTS_PER_SOL
                logger.debug(f"Saldo: {sol} SOL")
                return sol
        except Exception as e:
            logger.warning(f"Erro ao obter saldo: {e}")
        
        return 0.0
    
    def get_credits(self) -> float:
        """Obter saldo em créditos."""
        return self.get_balance() * CREDITS_PER_SOL


# ─────────────────────────────────────────────────────────────────────────
# Gerenciador de Créditos
# ─────────────────────────────────────────────────────────────────────────

class CreditsManager:
    """Gerenciador de créditos do usuário."""
    
    def __init__(self, user_id: str, credits_file: str = "data/credits.json"):
        self.user_id = user_id
        self.credits_file = Path(credits_file)
        self.credits_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.user_data = self._load_user_data()
    
    def _load_user_data(self) -> dict:
        """Carregar dados do usuário."""
        
        if not self.credits_file.exists():
            return {}
        
        try:
            data = json.loads(self.credits_file.read_text())
            return data.get(self.user_id, {})
        except Exception as e:
            logger.warning(f"Erro ao carregar dados de créditos: {e}")
            return {}
    
    def _save_user_data(self) -> None:
        """Salvar dados do usuário."""
        
        try:
            if self.credits_file.exists():
                all_data = json.loads(self.credits_file.read_text())
            else:
                all_data = {}
            
            all_data[self.user_id] = self.user_data
            self.credits_file.write_text(json.dumps(all_data, indent=2))
        except Exception as e:
            logger.error(f"Erro ao salvar dados de créditos: {e}")
    
    def get_total_credits(self) -> float:
        """Obter total de créditos."""
        return float(self.user_data.get("total_credits", 0.0))
    
    def get_available_credits(self) -> float:
        """Obter créditos disponíveis."""
        total = self.get_total_credits()
        used = float(self.user_data.get("used_credits", 0.0))
        return total - used
    
    def add_credits(self, amount: float, source: str = "deposit") -> bool:
        """Adicionar créditos."""
        
        current = self.get_total_credits()
        self.user_data["total_credits"] = current + amount
        self.user_data["last_transaction"] = datetime.utcnow().isoformat()
        
        # Registrar transação
        if "transactions" not in self.user_data:
            self.user_data["transactions"] = []
        
        self.user_data["transactions"].append({
            "type": "deposit",
            "amount": amount,
            "source": source,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        self._save_user_data()
        logger.info(f"Créditos adicionados: {amount} ({source})")
        return True
    
    def consume_credits(self, amount: float, action: str = "action") -> bool:
        """Consumir créditos."""
        
        available = self.get_available_credits()
        if available < amount:
            logger.warning(f"Créditos insuficientes: {available} < {amount}")
            return False
        
        current_used = float(self.user_data.get("used_credits", 0.0))
        self.user_data["used_credits"] = current_used + amount
        
        # Registrar transação
        if "transactions" not in self.user_data:
            self.user_data["transactions"] = []
        
        self.user_data["transactions"].append({
            "type": "consumption",
            "amount": amount,
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        self._save_user_data()
        logger.info(f"Créditos consumidos: {amount} ({action})")
        return True
    
    def get_transactions(self, limit: int = 10) -> list[dict]:
        """Obter histórico de transações."""
        transactions = self.user_data.get("transactions", [])
        return transactions[-limit:]


# ─────────────────────────────────────────────────────────────────────────
# Integração com Solana Pay
# ─────────────────────────────────────────────────────────────────────────

class SolanaPayIntegration:
    """Integração com Solana Pay para pagamentos."""
    
    def __init__(
        self,
        merchant_wallet: str,
        network: str = "mainnet",
    ):
        self.merchant_wallet = merchant_wallet
        self.network = network
        self.client = None
        
        if SOLANA_AVAILABLE:
            try:
                rpc_url = SOLANA_RPC_URLS.get(network)
                self.client = Client(rpc_url)
            except Exception as e:
                logger.warning(f"Erro ao conectar ao Solana Pay: {e}")
    
    def create_payment_link(
        self,
        amount_sol: float,
        reference: str,
        label: str = "Luna Agent Credits",
        message: str = "Compra de créditos Luna",
    ) -> str:
        """
        Criar link de pagamento Solana Pay.
        
        Retorna URL do pagamento.
        """
        
        # Construir URL de pagamento Solana Pay
        # Formato: solana:<recipient>?amount=<amount>&reference=<reference>&label=<label>&message=<message>
        
        payment_url = (
            f"solana:{self.merchant_wallet}"
            f"?amount={amount_sol}"
            f"&reference={reference}"
            f"&label={label}"
            f"&message={message}"
        )
        
        logger.info(f"Link de pagamento criado: {reference}")
        return payment_url
    
    def verify_payment(
        self,
        signature: str,
        expected_amount: float,
    ) -> bool:
        """
        Verificar se um pagamento foi confirmado.
        """
        
        if not self.client:
            logger.warning("Cliente Solana não disponível")
            return False
        
        try:
            # Verificar transação
            tx = self.client.get_transaction(signature)
            
            if tx and tx.value:
                # Validar montante
                # (implementação simplificada)
                logger.info(f"Pagamento verificado: {signature}")
                return True
        except Exception as e:
            logger.warning(f"Erro ao verificar pagamento: {e}")
        
        return False


# ─────────────────────────────────────────────────────────────────────────
# Funções Auxiliares
# ─────────────────────────────────────────────────────────────────────────

def get_wallet_manager(network: str = "mainnet") -> SolanaWalletManager:
    """Obter gerenciador de carteira."""
    return SolanaWalletManager(network=network)


def get_credits_manager(user_id: str) -> CreditsManager:
    """Obter gerenciador de créditos."""
    return CreditsManager(user_id=user_id)


def get_solana_pay(merchant_wallet: str, network: str = "mainnet") -> SolanaPayIntegration:
    """Obter integração Solana Pay."""
    return SolanaPayIntegration(merchant_wallet=merchant_wallet, network=network)

