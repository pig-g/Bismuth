# Lab 3: Signing Identity

Verify how a locally signed Bismuth transaction binds its sender, public key, signed fields, and transaction ID—and prove locally that changing one signed value invalidates the signature.

- **Time:** about 10 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** run the existing Lab 1 CLI in a local macOS or Linux Terminal

## Safety boundary

This lab uses an owned regnet node at `127.0.0.1:3030`, generated temporary wallets, and test BIS only. It has no mainnet connection, no remote fallback, and no real BIS.

The private key remains local inside the temporary Alice wallet. It is never printed and is never sent through node RPC. `identity` retrieves the already-confirmed public transaction, verifies it locally, and prints only a public-key SHA-256 fingerprint—not the full public key or signature. The tampered transaction is constructed and rejected locally; it is never submitted to the node.

## 1. Start the existing CLI

From the repository root:

```bash
.venv/bin/python ./labs/01-test-bis-workflow/cli.py
```

Wait for the `regnet>` prompt.

## 2. Create identities and fund Alice

```text
wallets
```

Alice and Bob are generated for this temporary session. Their addresses are public identifiers; their private keys remain local.

```text
mine 1
```

This gives Alice test BIS for the exercise.

## 3. Sign and send locally

```text
send alice bob 1
```

The exact signed tuple is:

```text
(timestamp, address, recipient, amount, operation, openfield)
```

The signature is produced by Alice's private key on the client side. The node receives the signed transaction and verifies the signature plus the public-key/address relationship before accepting it.

Confirm it in a block:

```text
mine 1
```

## 4. Verify transaction identity

```text
identity last
```

Expected booleans:

```json
{
  "signature_valid": true,
  "address_matches_public_key": true,
  "txid_matches_signature_prefix": true,
  "tampered_amount_rejected": true
}
```

The output also includes:

```text
public_key_sha256
```

This fingerprint lets you recognize the public key without printing its full encoded value.

### Interpret each result

- `signature_valid`: the public key verifies the signature over the original six signed fields.
- `address_matches_public_key`: deriving the sender address from the public key reproduces the transaction's `address`.
- `txid_matches_signature_prefix`: the named Bismuth transaction ID equals `signature[:56]`. It is not the block hash and is not a lowercase-hex hash.
- `tampered_amount_rejected`: changing the amount locally by `0.00000001` while keeping the original signature fails verification.
- `public_key_sha256`: a display fingerprint only; it is not the Bismuth address or txid.

The command performs independent local verification using the same `SignerFactory` validation rule used by the node. It does not ask the node to sign and does not submit the tampered tuple.

## 5. Clean up

```text
quit
```

The owned node, generated wallets, SQLite ledger, and all temporary session files are removed.

## What you learned

```text
private key stays local
→ six transaction fields are signed
→ public key verifies the signature
→ public key binds to sender address
→ signature prefix names the txid
→ any signed-field tampering is rejected
```

Lab 2 followed transaction state. Lab 2.1 followed persistence. Lab 3 explains why the transaction has a verifiable identity.
