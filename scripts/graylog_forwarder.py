#!/usr/bin/env python3
"""
Freqtrade Log Forwarder to Graylog

Sends Freqtrade logs to Graylog via GELF (Graylog Extended Log Format).
Runs as a background process tailing the bot log file.

Usage:
    python graylog_forwarder.py [--host GRAYLOG_HOST] [--port PORT]
"""

import socket
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
import os

# Graylog GELF configuration
DEFAULT_GRAYLOG_HOST = "192.168.2.2"  # Docker host where Graylog runs
DEFAULT_GRAYLOG_PORT = 12201  # GELF UDP port
LOG_FILE = Path("/a0/usr/workdir/freqtrade/user_data/logs/bot.log")
STATE_FILE = Path("/tmp/graylog_forwarder_position.txt")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_graylog_host():
    """Get Graylog host from environment or default."""
    return os.environ.get('GRAYLOG_HOST', DEFAULT_GRAYLOG_HOST)


def get_graylog_port():
    """Get Graylog port from environment or default."""
    return int(os.environ.get('GRAYLOG_PORT', DEFAULT_GRAYLOG_PORT))


def create_gelf_message(log_line: str, source: str = "freqtrade") -> dict:
    """Create a GELF message from a log line."""
    # Parse log line
    timestamp = datetime.now().isoformat()
    level = "INFO"
    
    # Extract level from log line
    if " - ERROR - " in log_line:
        level = "ERROR"
    elif " - WARNING - " in log_line:
        level = "WARNING"
    elif " - DEBUG - " in log_line:
        level = "DEBUG"
    
    gelf_message = {
        "version": "1.1",
        "host": socket.gethostname(),
        "short_message": log_line,
        "timestamp": time.time(),
        "level": level,
        "_source": source,
        "_application": "freqtrade",
        "_log_type": "trading"
    }
    
    return gelf_message


def send_to_graylog(message: dict, host: str, port: int) -> bool:
    """Send GELF message to Graylog via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        data = json.dumps(message).encode('utf-8')
        sock.sendto(data, (host, port))
        sock.close()
        return True
    except Exception as e:
        logger.error(f"Failed to send to Graylog: {e}")
        return False


def read_last_position() -> int:
    """Read the last file position from state file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return int(f.read().strip())
        except:
            return 0
    return 0


def save_last_position(position: int):
    """Save the current file position to state file."""
    with open(STATE_FILE, 'w') as f:
        f.write(str(position))


def tail_log_file(host: str, port: int):
    """Tail the log file and send new lines to Graylog."""
    logger.info(f"Starting log forwarder: {LOG_FILE} -> {host}:{port}")
    
    # Wait for log file to exist
    while not LOG_FILE.exists():
        logger.warning(f"Log file not found: {LOG_FILE}")
        time.sleep(5)
    
    last_pos = read_last_position()
    
    while True:
        try:
            with open(LOG_FILE, 'r') as f:
                # Seek to last position
                f.seek(last_pos)
                
                # Read new lines
                for line in f:
                    line = line.strip()
                    if line:
                        message = create_gelf_message(line)
                        if send_to_graylog(message, host, port):
                            pass  # Successfully sent
                        
                # Update position
                last_pos = f.tell()
                save_last_position(last_pos)
            
            # Sleep before next check
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='Freqtrade Log Forwarder to Graylog')
    parser.add_argument('--host', default=get_graylog_host(), help='Graylog host')
    parser.add_argument('--port', type=int, default=get_graylog_port(), help='Graylog GELF port')
    args = parser.parse_args()
    
    logger.info(f"Graylog forwarder starting: {args.host}:{args.port}")
    tail_log_file(args.host, args.port)


if __name__ == '__main__':
    main()
