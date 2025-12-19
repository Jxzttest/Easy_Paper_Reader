import os
import logging


# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(__file__), "log")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "app.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)