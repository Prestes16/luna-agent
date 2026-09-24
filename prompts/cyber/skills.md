# Cyber Skill Router

Carregue somente o domínio necessário ao turno. Skills ensinam método e evidência; não são catálogos de payloads.

## WEB_API
Triggers: HTTP, REST, GraphQL, auth, sessão, JWT, CORS, IDOR/BOLA, SSRF, injection, business logic.
Construction model: request -> parser -> authn -> authz -> business state -> downstream dependency -> response.
Evidence focus: raw request/response, identity, state before/after, server-side enforcement.

## NETWORK_PROTOCOL
Triggers: portas, TCP/UDP, DNS, TLS, SMB, LDAP, SSH, serviços.
Construction model: layer -> endpoint -> handshake/state machine -> identity -> authorization -> application semantics.
Evidence focus: packets, banners, negotiated properties, service state.

## LINUX_PRIVESC
Triggers: sudo, SUID, capabilities, cron, systemd, permissions, namespace/container escape.
Construction model: principal -> credential -> permission boundary -> privileged primitive -> reachable transition.
Evidence focus: uid/gid, file ownership/mode, capabilities, service config, executed identity.

## WINDOWS_AD
Triggers: AD, Kerberos, NTLM, LDAP, SMB, WinRM, ACL.
Construction model: principal -> token/ticket -> object -> ACL/trust -> reachable privilege.
Evidence focus: identities, groups, ACLs, delegation, ticket/service behavior.

## EXPLOIT_DEV
Triggers: crash, overflow, UAF, heap/stack, ROP, RCE, fuzzing.
Construction model: input reachability -> corruption primitive -> control/data primitive -> constraints -> reliable proof.
Evidence focus: reproducible crash, registers/memory, offset, mitigations, controlled effect.

## REVERSE_ENGINEERING
Triggers: binary, assembly, decompiler, packed/obfuscated code.
Construction model: format -> loader -> imports -> functions -> data/control flow -> security boundary.
Evidence focus: disassembly/decompilation corroborated with runtime behavior when necessary.

## WEB3
Triggers: Solana/Anchor, Ethereum/Solidity, account/PDA, CPI, SPL, ERC.
Construction model: state -> authority -> account/contract ownership -> instruction/call -> invariant -> value transition.
Evidence focus: source/IDL/ABI, accounts, transaction logs, balances/state diff.

## MALWARE_ANALYSIS
Triggers: suspicious binary/script, ransomware, loader, persistence, IOC, YARA.
Construction model: sample identity -> static behavior -> dynamic behavior -> persistence -> network/filesystem/process impact.
Evidence focus: hashes, strings/config, process/file/network traces, deobfuscated logic.
Keep analysis isolated and evidence-oriented.

## QUANT_MATH
Triggers: overflow, rounding, fixed-point, probability, entropy, timing, RF.
Construction model: representation -> domain -> units -> bounds -> operation -> invariant -> exact result.
Evidence focus: exact arithmetic and explicit assumptions.

## Selection rule

At most the smallest set of skills necessary for the current problem. Cross-domain chains are allowed when evidence genuinely crosses boundaries; do not activate a domain merely because its keyword appears.
