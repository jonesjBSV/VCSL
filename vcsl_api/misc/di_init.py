from kink import di
from os import environ
from persistance.datastore_postgres import PostgresDataStore
from services.abstractClasses.serv_cache_i import ICacheService
from services.abstractClasses.serv_lock_i import ILockService
from services.serv_bsv import BsvService
from services.serv_lock import LockService
from services.serv_cache import CacheService
from services.serv_ipfs import IPFSService
from redis import Redis


def init_di() -> None:
    di['redis_host'] = environ.get('REDIS_HOST', '127.0.0.1')
    di['redis_port'] = environ.get('REDIS_PORT', 6379)
    di[Redis] = Redis(host=di['redis_host'], port=di['redis_port'], db=0)

    di['psql_host'] = environ.get('PSQL_HOST', '127.0.0.1')
    di['psql_port'] = environ.get('PSQL_PORT', 5432)
    di['psql_user'] = environ.get('PSQL_USER', 'postgres')
    di['psql_pass'] = environ.get('PSQL_PASS', '12345')
    di['psql_db'] = environ.get('PSQL_DB', 'vcsl')
    di[PostgresDataStore] = PostgresDataStore(dbname=di['psql_db'], dbuser=di['psql_user'], dbpassword=di['psql_pass'], dbhost=di['psql_host'], dbport=di['psql_port'])
    connected = di[PostgresDataStore].init_connections()
    if not connected:
        raise Exception("Unable to connect to postgres")

    di['bsv_network'] = environ.get('BSV_NETWORK', 'testnet')

    di['ipfs_api_url'] = environ.get('IPFS_API_URL', 'http://localhost:4243')
    di[IPFSService] = IPFSService(ipfs_api_url=di['ipfs_api_url'])

    di[BsvService] = BsvService(db_service=di[PostgresDataStore], bsv_network=di['bsv_network'])

    di[ICacheService] = CacheService()
    di[ILockService] = LockService()
    # di[HealthCheckService] = HealthCheckService()
    # di[RedisService] = RedisService()
    # di[HealthCheckRouter] = HealthCheckRouter()
    # di[BitArrayService] = BitArrayService()
    # di[BitArrayRouter] = BitArrayRouter()
    # di[BitArrayDAO] = BitArrayDAO()
