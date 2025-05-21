import psycopg as pg
from psycopg_pool import ConnectionPool
import sys
from typing import Optional, Tuple


class PostgresDataStore():
    def __init__(self, dbname: str, dbuser: str, dbpassword: str, dbhost: str, dbport: str):
        self.dbname = dbname
        self.dbuser = dbuser
        self.dbpassword = dbpassword
        self.dbhost = dbhost
        self.dbport = dbport
        self.conninfo = f"dbname={dbname} user={dbuser} password={dbpassword} host={dbhost} port={dbport}"
        self.pool: Optional[ConnectionPool] = None

    def init_connections(self, minconn: int = 1, maxconn: int = 3) -> bool:
        try:
            # Use ConnectionPool (suitable for threaded environments too)
            self.pool = ConnectionPool(self.conninfo, min_size=minconn, max_size=maxconn)
            # Test the connection pool
            with self.pool.connection() as conn:
                conn.execute("SELECT 1") # Simple query to ensure connection works
            print("Postgres connection pool initialized successfully.")
            return True
        except Exception as e:
            print(f"Unable to connect to postgres: {e}", file=sys.stderr)
            self.pool = None
            return False

    def store_issuer_url(self, issuer_id: str, url: str, txid: Optional[str] = None) -> None:
        """Stores or updates an issuer URL and its associated transaction ID."""
        if not self.pool:
            raise Exception("Connection pool not initialized. Call init_connections first.")

        sql = """
        INSERT INTO issuer_urls (issuer_id, url, txid)
        VALUES (%s, %s, %s)
        ON CONFLICT (issuer_id) DO UPDATE SET
          url = EXCLUDED.url,
          txid = EXCLUDED.txid;
        """
        try:
            # Use the pool as a context manager
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (issuer_id, url, txid))
                    conn.commit() # Ensure the transaction is committed
        except Exception as e:
            print(f"Error storing issuer URL: {e}", file=sys.stderr)
            # Optionally re-raise or handle the error appropriately
            raise

    def get_issuer_url(self, issuer_id: str) -> Optional[Tuple[str, Optional[str]]]:
        """Retrieves the URL and optional transaction ID for a given issuer ID."""
        if not self.pool:
            raise Exception("Connection pool not initialized. Call init_connections first.")

        sql = "SELECT url, txid FROM issuer_urls WHERE issuer_id = %s;"
        try:
            # Use the pool as a context manager
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (issuer_id,))
                    result = cur.fetchone()
                    return result if result else None
        except Exception as e:
            print(f"Error retrieving issuer URL for {issuer_id}: {e}", file=sys.stderr)
            # Optionally re-raise or handle the error appropriately
            raise

    def store_vcsl(self, id: str, ipns: str, txid: str) -> None:
        """Stores or updates a VCSL entry (ID, IPNS link, and transaction ID)."""
        if not self.pool:
            raise Exception("Connection pool not initialized. Call init_connections first.")

        sql = """
        INSERT INTO vcsl_data (vcsl_id, ipns, txid)
        VALUES (%s, %s, %s)
        ON CONFLICT (vcsl_id) DO UPDATE SET
          ipns = EXCLUDED.ipns,
          txid = EXCLUDED.txid;
        """
        try:
            # Use the pool as a context manager
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (id, ipns, txid))
                    conn.commit() # Ensure the transaction is committed
        except Exception as e:
            print(f"Error storing VCSL data for {id}: {e}", file=sys.stderr)
            # Optionally re-raise or handle the error appropriately
            raise

    def get_vcsl(self, id: str) -> Optional[Tuple[str, str]]:
        """Retrieves the IPNS link and transaction ID for a given VCSL ID."""
        if not self.pool:
            raise Exception("Connection pool not initialized. Call init_connections first.")

        sql = "SELECT ipns, txid FROM vcsl_data WHERE vcsl_id = %s;"
        try:
            # Use the pool as a context manager
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (id,))
                    result = cur.fetchone()
                    return result if result else None
        except Exception as e:
            print(f"Error retrieving VCSL data for {id}: {e}", file=sys.stderr)
            # Optionally re-raise or handle the error appropriately
            raise
