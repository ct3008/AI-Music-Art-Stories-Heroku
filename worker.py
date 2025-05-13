import os
import redis
from rq import Worker, Queue, Connection
from urllib.parse import urlparse
import ssl

from redis_config import get_redis_connection

# Now you can use the same connection everywhere
redis_conn = get_redis_connection()

# redis_conn.ssl_context.verify_mode = ssl.CERT_NONE  # Disable verification

# Listen to the default queue
if __name__ == "__main__":
    with Connection(redis_conn):
        worker = Worker(["default"])
        worker.work()
