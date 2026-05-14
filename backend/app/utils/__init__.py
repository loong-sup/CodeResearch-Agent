# set global timezone
import os
import pytz  
from datetime import datetime

os.environ['TZ'] = 'Asia/Shanghai' 

tz = pytz.timezone('Asia/Shanghai')
current_time = datetime.now(tz)
print(current_time)

from .get_logger import get_logger
logger = get_logger()