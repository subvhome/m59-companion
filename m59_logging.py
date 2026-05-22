import logging
import sys
import os

# Create a central logger
logger = logging.getLogger("m59")

def setup_logging(debug_enabled=False):
    """
    Configures the global logging settings.
    Errors/Warnings/Info always go to stdout and file.
    Debug messages only if debug_enabled is True.
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        try:
            os.makedirs("logs")
        except:
            pass

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Root logger level (we set it to DEBUG so we can control child loggers)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler (stdout)
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    c_format = logging.Formatter(log_format)
    c_handler.setFormatter(c_format)
    root_logger.addHandler(c_handler)

    # File Handler (logs/companion_debug.log)
    try:
        f_handler = logging.FileHandler("logs/companion_debug.log", encoding="utf-8")
        f_handler.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
        f_format = logging.Formatter(log_format)
        f_handler.setFormatter(f_format)
        root_logger.addHandler(f_handler)
    except Exception as e:
        print(f"CRITICAL: Could not initialize log file: {e}")

    logger.info(f"Logging initialized (Debug: {debug_enabled})")

def get_logger(name=None):
    if name:
        return logging.getLogger(f"m59.{name}")
    return logger
