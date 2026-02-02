from rq import Queue
from redis import Redis

redis_conn = Redis(host="localhost",port=6379)
task_queue = Queue("code_queue",connection=redis_conn)

