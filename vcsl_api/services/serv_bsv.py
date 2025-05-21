import os
import hmac
import hashlib
import requests 
from kink import inject
from typing import List, Optional, Tuple

from bsvlib import Wallet, Key
from bsvlib.constants import Chain
from bsvlib.curve import N # Import N from curve.py
from bsvlib.script.script import Script # Import from script.script
from bsvlib.transaction.transaction import Tx, TxOutput # Import from transaction.transaction

from persistance.datastore_postgres import PostgresDataStore
# Assuming a BRC-42 implementation exists or needs to be added/adapted
# from bsvlib.brc import derive_child_key # Placeholder for BRC-42 derivation

# Define a BRC-42 Protocol ID for VCSL Anchoring
VCSL_PROTOCOL_ID = "quarkid-vcsl" 

# WOC API endpoint
WOC_API_BASE_URL = "https://api.whatsonchain.com/v1/bsv"

@inject # Assuming kink is used for DI
class BsvService:
    # Placeholder type for DbService - replace with actual import
    def __init__(self, db_service: object, bsv_network: str = 'testnet'):
        """
        Initializes the BSV Service.
        
        Args:
            db_service: The injected database service instance.
            bsv_network: The BSV network ('mainnet' or 'testnet'). Defaults to 'testnet'.
        """
        self.db_service = db_service
        self.network = bsv_network
        
        # Load private key from environment variable (ensure BSV_WIF_KEY is set)
        wif_key = os.getenv("BSV_WIF_KEY")
        if not wif_key:
            raise ValueError("BSV_WIF_KEY environment variable not set.")
        self.wallet_key = Key(wif_key, network=self.network)
        
        print(f"Initialized BSV Service for network: {self.network}")
        print(f"Using wallet address: {self.wallet_key.address()}")
        
        # TODO: Add connection setup for broadcasting transactions if needed 
        # (e.g., using ARC, WhatsOnChain API, etc.)
        # self.broadcast_api = ... 

    def _derive_brc42_key(self, key_id: str, protocol: str = VCSL_PROTOCOL_ID) -> Key:
        """
        Derives a child key using an adapted BRC-42 like scheme based on HMAC-SHA256.

        Args:
            key_id: The specific identifier for this key context (e.g., "vcsl/some_id").
            protocol: The protocol identifier (defaults to VCSL_PROTOCOL_ID).

        Returns:
            The derived Key object.
        """
        # Use the master private key bytes as the HMAC key
        hmac_key = self.wallet_key.private_bytes()

        # Construct the context string (previously "invoice number")
        context_string = f"{protocol}/{key_id}"
        message = context_string.encode('utf-8')

        # Calculate HMAC-SHA256
        hmac_digest = hmac.new(hmac_key, message, hashlib.sha256).digest()

        # Convert HMAC digest to a scalar integer
        scalar = int.from_bytes(hmac_digest, 'big')

        # Get the master private key scalar
        master_scalar = self.wallet_key.private_int()

        # Add the scalar to the master private key scalar (modulo N, the curve order)
        # Use the imported N
        child_scalar = (master_scalar + scalar) % N

        # Create the derived Key object from the new scalar
        derived_key = Key.from_int(child_scalar, network=self.network)

        print(f"Derived key for context '{context_string}': {derived_key.address()}")
        return derived_key

    def _fetch_utxos(self, address: str) -> list:
        """
        Fetches UTXOs for a given address using the WhatsOnChain API.
        """
        print(f"Fetching UTXOs for address: {address} on {self.network}")
        url = f"{WOC_API_BASE_URL}/{self.network}/address/{address}/unspent"
        try:
            response = requests.get(url)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            data = response.json()

            utxos = []
            for utxo_data in data:
                # Ensure value is treated as integer (sats)
                sats = int(utxo_data.get('value', 0))
                txid = utxo_data.get('tx_hash')
                index = utxo_data.get('tx_pos')

                if sats > 0 and txid and isinstance(index, int):
                    # We need the scriptPubKey hex for bsvlib Tx.add_input
                    # WOC doesn't provide it directly in /unspent, fetch from tx details?
                    # For now, we'll assume P2PKH and derive it.
                    # WARNING: This assumption might be incorrect if the UTXO is not P2PKH!
                    # A more robust solution would fetch the scriptPubKey from the source tx.
                    script_pubkey_hex = Script.p2pkh(address).hex()

                    utxos.append({
                        'txid': txid,
                        'index': index,
                        'sats': sats,
                        'script_pubkey': script_pubkey_hex # IMPORTANT: Assumption!
                    })
                else:
                    print(f"Skipping invalid UTXO data: {utxo_data}")

            print(f"Found {len(utxos)} UTXOs.")
            return utxos

        except requests.exceptions.RequestException as e:
            print(f"ERROR fetching UTXOs for {address}: {e}")
            return [] # Return empty list on error
        except Exception as e:
            print(f"ERROR processing UTXO data for {address}: {e}")
            return []

    def _create_anchor_tx(self, derived_key: Key) -> Tx:
        """
        Creates a simple BSV transaction to anchor data using the derived key.
        Sends a dust amount to the derived key's address from the main wallet key.
        """
        # Fetch UTXOs for the main wallet key
        utxos = self._fetch_utxos(self.wallet_key.address())
        if not utxos:
            raise Exception(f"No spendable UTXOs found for address {self.wallet_key.address()}")

        # Select a suitable UTXO - for now, just use the first one found
        # TODO: Implement better UTXO selection logic (e.g., find smallest UTXO > dust + fee)
        utxo_to_spend = utxos[0]
        print(f"Selected UTXO to spend: {utxo_to_spend['txid']}:{utxo_to_spend['index']} ({utxo_to_spend['sats']} sats)")

        t = Tx(network=self.network)
        # Add the selected UTXO as input
        t.add_input(
            txid=utxo_to_spend['txid'],
            index=utxo_to_spend['index'],
            sats=utxo_to_spend['sats'],
            script_pubkey=utxo_to_spend['script_pubkey'] # Using derived script, see warning above
        )

        # Output to the derived key's address (P2PKH) - dust amount
        dust_amount = 546 # Minimum spendable amount
        t.add_output(TxOutput(sats=dust_amount, script_pubkey=Script.p2pkh(derived_key.address())))

        # --- Fee Calculation ---
        # Define a standard fee rate (sats/byte)
        fee_rate = 0.5 # Standard rate, can be made configurable

        # Estimate transaction size BEFORE adding change output and signing
        # Add temporary placeholder change output to estimate size correctly
        # This is a slight approximation as the final change amount isn't known yet,
        # but usually sufficient for fee calculation.
        temp_change_sats = 1 # Placeholder for size estimation
        temp_change_script = Script.p2pkh(self.wallet_key.address())
        t.add_output(TxOutput(sats=temp_change_sats, script_pubkey=temp_change_script))

        # Estimate size (using bsvlib's Tx.estimated_size())
        # NOTE: Ensure this method exists and works as expected in your bsvlib version.
        estimated_size_bytes = t.estimated_size()
        # Remove temporary change output
        t.outputs.pop()

        # Calculate fee
        fee = int(estimated_size_bytes * fee_rate)
        # Ensure minimum fee (e.g., 1 sat)
        fee = max(1, fee)
        print(f"Estimated size: {estimated_size_bytes} bytes, Fee rate: {fee_rate} sat/byte, Calculated fee: {fee} sat")
        # --- End Fee Calculation ---

        # Calculate change
        change_sats = utxo_to_spend['sats'] - dust_amount - fee
        if change_sats < 0:
            # Not enough funds in the chosen UTXO for dust + fee
            # TODO: Implement logic to try another UTXO or raise a more specific error
            raise Exception(f"Insufficient funds in selected UTXO {utxo_to_spend['txid']}:{utxo_to_spend['index']}. Needed: {dust_amount + fee}, Available: {utxo_to_spend['sats']}.")

        # Add change output back to the wallet key if change is significant (>= dust)
        if change_sats >= dust_amount: # Only add change if it's spendable
            t.add_output(TxOutput(sats=change_sats, script_pubkey=Script.p2pkh(self.wallet_key.address())))
            print(f"Adding change output: {change_sats} sats")
        else:
            # If change is less than dust, it's effectively burned (goes to miner)
            print(f"Change amount ({change_sats} sats) is less than dust threshold ({dust_amount} sats), not adding change output.")

        # Sign the input spending from the main wallet key
        # Ensure the key corresponding to the UTXO's scriptPubKey is used for signing
        t.sign(keys=[self.wallet_key])

        print(f"Created anchor TX: {t.txid()}")
        return t

    def _broadcast_tx(self, tx: Tx) -> str:
        """
        Broadcasts the signed transaction using the WhatsOnChain API.
        """
        tx_hex = tx.hex()
        print(f"Broadcasting TX: {tx.txid()} ({len(tx_hex)//2} bytes)")
        url = f"{WOC_API_BASE_URL}/{self.network}/tx/raw"
        payload = {"txhex": tx_hex}

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes

            # WOC returns the txid directly on success (sometimes quoted)
            txid_response = response.text.strip().strip('"')

            if txid_response == tx.txid():
                print(f"Broadcast successful, TXID: {txid_response}")
                return txid_response
            else:
                # This case might indicate an issue or unexpected API response format
                print(f"WARNING: Broadcast API returned unexpected response: {txid_response}")
                # We might still return the calculated txid if we trust our calculation
                # Or raise an error depending on desired strictness.
                # For now, return our calculated txid but log the warning.
                return tx.txid()

        except requests.exceptions.RequestException as e:
            print(f"ERROR broadcasting transaction {tx.txid()}: {e}")
            # Consider the error response content if available
            if e.response is not None:
                print(f"Error response: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Failed to broadcast transaction: {e}") # Re-raise to signal failure

    def set_issuer_url(self, issuer_id: str, new_issuer_url: str) -> str | None:
        """
        Updates the issuer URL off-chain and optionally anchors the change on BSV.
        
        Args:
            issuer_id: A unique identifier for the issuer.
            new_issuer_url: The new URL to set.

        Returns:
            The BSV transaction ID if anchored, otherwise None.
        """
        print(f"Updating issuer URL for {issuer_id} to {new_issuer_url}")
        # Update issuer URL in the database
        try:
            # Assuming DbService has this method
            self.db_service.update_issuer_url(issuer_id=issuer_id, new_url=new_issuer_url)
            print(f"Issuer URL updated in DB for {issuer_id}")
        except Exception as db_err:
            print(f"ERROR: Database update failed for issuer URL {issuer_id}: {db_err}")
            # Decide if DB failure should prevent anchoring. Likely yes.
            raise Exception(f"Failed to update issuer URL in database: {db_err}")

        # Optional: Anchor this change on-chain
        try:
            derived_key = self._derive_brc42_key(key_id=f"issuer/{issuer_id}")
            anchor_tx = self._create_anchor_tx(derived_key)
            txid = self._broadcast_tx(anchor_tx)
            # Store the anchor txid in the database
            try:
                # Assuming DbService has this method
                self.db_service.store_issuer_anchor(issuer_id=issuer_id, txid=txid)
                print(f"Stored anchor txid {txid} for issuer {issuer_id}")
            except Exception as db_err:
                # Log the error but don't necessarily fail the whole operation,
                # as the anchor exists on-chain. Might need reconciliation later.
                print(f"WARNING: Failed to store anchor txid {txid} in DB for issuer {issuer_id}: {db_err}")
            
            return txid
        except Exception as e:
            print(f"ERROR: Failed to anchor issuer URL update: {e}")
            # Decide if failure to anchor should prevent the off-chain update 
            # or just be logged. For now, we proceed with off-chain update.
            return None 

    def add_vcsl(self, id: str, ipns: str) -> str:
        """
        Stores VCSL data off-chain and anchors the update on BSV.
        
        Args:
            id: The unique identifier for the VCSL.
            ipns: The IPNS hash or other pointer to the VCSL data.

        Returns:
            The BSV transaction ID for the anchor.
        """
        print(f"Adding VCSL entry for ID: {id}, IPNS: {ipns}")
        # Anchor the update on-chain first
        try:
            derived_key = self._derive_brc42_key(key_id=f"vcsl/{id}")
            anchor_tx = self._create_anchor_tx(derived_key)
            txid = self._broadcast_tx(anchor_tx)
            print(f"Successfully anchored VCSL update for {id}, TXID: {txid}")
        except Exception as e:
            print(f"ERROR: Failed to anchor VCSL update for {id}: {e}")
            # If anchoring fails, we cannot proceed with storing in DB
            raise Exception(f"Failed to create BSV anchor for VCSL {id}: {e}")

        # Store the VCSL data along with the anchor txid in the database
        try:
            # Assuming DbService has this method
            self.db_service.store_vcsl(id=id, ipns=ipns, txid=txid)
            print(f"Stored VCSL entry {id} in DB with anchor txid {txid}")
            return txid
        except Exception as db_err:
            print(f"ERROR: Database store failed for VCSL {id} (anchor txid {txid}): {db_err}")
            # Anchoring succeeded, but DB store failed. Requires attention/reconciliation.
            # Raise an exception to signal the inconsistency.
            raise Exception(f"VCSL {id} anchored ({txid}), but failed to store in DB: {db_err}")

    def get_issuer_url(self, issuer_id: str) -> str | None:
        """
        Retrieves the issuer URL from the database.

        Args:
            issuer_id: The identifier for the issuer.

        Returns:
            The issuer URL if found, otherwise None.
        """
        print(f"Getting issuer URL for {issuer_id}")
        try:
            # Assuming DbService has this method
            url = self.db_service.get_issuer_url(issuer_id=issuer_id)
            print(f"Retrieved issuer URL for {issuer_id}: {'Found' if url else 'Not found'}")
            return url
        except Exception as db_err:
            print(f"ERROR: Database query failed for issuer URL {issuer_id}: {db_err}")
            return None # Return None on DB error

    def get_vcsl(self, id: str) -> tuple[str | None, str | None]:
        """
        Retrieves the VCSL data (IPNS/pointer) and its anchor TXID from the database.

        Args:
            id: The identifier for the VCSL.

        Returns:
            A tuple containing (ipns, txid) if found, otherwise (None, None).
        """
        print(f"Getting VCSL data for {id}")
        try:
            # Assuming DbService has this method returning (ipns, txid)
            ipns, txid = self.db_service.get_vcsl(id=id)
            print(f"Retrieved VCSL data for {id}: {'Found' if ipns else 'Not found'}")
            return ipns, txid
        except Exception as db_err:
            print(f"ERROR: Database query failed for VCSL {id}: {db_err}")
            return None, None # Return (None, None) on DB error
