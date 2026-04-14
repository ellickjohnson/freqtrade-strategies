import requests_unixsocket

requests_unixsocket.monkeypatch()

import docker
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from pathlib import Path
import os


class ContainerManager:
    def __init__(self):
        self._client = None
        self._api_client = None
        self.containers: Dict[str, str] = {}

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    @property
    def api_client(self):
        if self._api_client is None:
            self._api_client = docker.APIClient()
        return self._api_client

    def _get_container_name(self, strategy_id: str) -> str:
        return f"freqtrade-{strategy_id}"

    def _get_volume_mounts(
        self, strategy_id: str, config_path: str, strategy_file: str
    ) -> Dict[str, Dict[str, str]]:
        host_project_root = os.environ.get("HOST_PROJECT_ROOT", "/app")
        host_config_path = f"{host_project_root}/config/{strategy_id}.json"
        host_user_data = f"{host_project_root}/user_data/{strategy_id}"

        return {
            host_config_path: {
                "bind": "/freqtrade/config.json",
                "mode": "rw",
            },
            f"{host_project_root}/strategies": {
                "bind": "/freqtrade/user_data/strategies",
                "mode": "ro",
            },
            host_user_data: {"bind": "/freqtrade/user_data", "mode": "rw"},
        }

    async def create_container(
        self, strategy_id: str, config: Dict[str, Any], port: int, strategy_file: str
    ) -> str:
        container_name = self._get_container_name(strategy_id)

        try:
            existing = self.client.containers.list(
                all=True, filters={"name": container_name}
            )
            if existing:
                existing[0].remove(force=True)
        except docker.errors.NotFound:
            pass

        volumes = self._get_volume_mounts(
            strategy_id,
            config.get("config_path", f"/configs/{strategy_id}.json"),
            strategy_file,
        )

        container = self.client.containers.create(
            image=config.get("image", "freqtradeorg/freqtrade:stable"),
            command=f"trade --strategy {strategy_file} --config /freqtrade/config.json",
            name=container_name,
            volumes=volumes,
            ports={"8080/tcp": port},
            environment={
                "FREQTRADE__API_SERVER__ENABLED": "true",
                "FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS": "0.0.0.0",
                "FREQTRADE__API_SERVER__LISTEN_PORT": "8080",
            },
            detach=True,
            labels={"strategy_id": strategy_id, "managed_by": "freqtrade-manager"},
        )

        return container.id

    async def start_container(self, strategy_id: str) -> bool:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            container.start()

            await asyncio.sleep(2)

            container.reload()
            if container.status != "running":
                raise Exception(f"Container failed to start: {container.status}")

            return True
        except docker.errors.NotFound:
            raise Exception(f"Container {container_name} not found")
        except Exception as e:
            raise Exception(f"Error starting container: {e}")

    async def stop_container(self, strategy_id: str, timeout: int = 10) -> bool:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            container.stop(timeout=timeout)
            return True
        except docker.errors.NotFound:
            return True
        except Exception as e:
            raise Exception(f"Error stopping container: {e}")

    async def remove_container(self, strategy_id: str) -> bool:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            await self.stop_container(strategy_id)
            container.remove()
            return True
        except docker.errors.NotFound:
            return True
        except Exception as e:
            raise Exception(f"Error removing container: {e}")

    async def get_container_status(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            container.reload()

            started_at = None
            if container.attrs.get("State", {}).get("StartedAt"):
                started_at = container.attrs["State"]["StartedAt"]

            return {
                "container_id": container.id,
                "container_name": container.name,
                "status": container.status,
                "started_at": started_at,
                "image": container.attrs.get("Config", {}).get("Image"),
                "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
            }
        except docker.errors.NotFound:
            return None

    async def get_container_logs(self, strategy_id: str, tail: int = 100) -> List[str]:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8").split("\n")
        except docker.errors.NotFound:
            return []
        except Exception as e:
            print(f"Error getting logs: {e}")
            return []

    async def execute_in_container(
        self, strategy_id: str, command: str
    ) -> Optional[str]:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            exit_code, output = container.exec_run(command)

            if exit_code == 0:
                return output.decode("utf-8")
            else:
                raise Exception(f"Command failed with exit code {exit_code}")
        except docker.errors.NotFound:
            raise Exception(f"Container {container_name} not found")
        except Exception as e:
            raise Exception(f"Error executing command: {e}")

    async def get_container_stats(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            stats = container.stats(stream=False)

            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            cpu_system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )

            cpu_percent = (
                (cpu_delta / cpu_system_delta) * 100 if cpu_system_delta > 0 else 0
            )

            mem_usage = stats["memory_stats"]["usage"]
            mem_limit = stats["memory_stats"]["limit"]
            mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_usage": mem_usage,
                "memory_limit": mem_limit,
                "memory_percent": round(mem_percent, 2),
                "network_rx": stats["networks"]["eth0"]["rx_bytes"]
                if "networks" in stats
                else 0,
                "network_tx": stats["networks"]["eth0"]["tx_bytes"]
                if "networks" in stats
                else 0,
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return None

    async def health_check(self, strategy_id: str) -> Dict[str, Any]:
        status = await self.get_container_status(strategy_id)

        if not status:
            return {
                "healthy": False,
                "status": "not_found",
                "message": "Container not found",
            }

        if status["status"] != "running":
            return {
                "healthy": False,
                "status": status["status"],
                "message": f"Container is {status['status']}",
            }

        try:
            import asyncio
            import aiohttp

            port = None
            for container_port, host_ports in status.get("ports", {}).items():
                if container_port == "8080/tcp" and host_ports:
                    port = host_ports[0]["HostPort"]
                    break

            if not port:
                return {
                    "healthy": False,
                    "status": "running",
                    "message": "Could not determine API port",
                }

            api_url = f"http://localhost:{port}/api/v1/ping"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=2) as response:
                    if response.status == 200:
                        return {
                            "healthy": True,
                            "status": "running",
                            "api_responding": True,
                            "port": port,
                        }
                    else:
                        return {
                            "healthy": False,
                            "status": "running",
                            "api_responding": False,
                            "message": f"API returned status {response.status}",
                        }
        except Exception as e:
            return {
                "healthy": False,
                "status": "running",
                "api_responding": False,
                "message": str(e),
            }

    async def list_managed_containers(self) -> List[Dict[str, Any]]:
        containers = self.client.containers.list(all=True)

        managed = []
        for container in containers:
            labels = container.attrs.get("Config", {}).get("Labels", {})
            if labels.get("managed_by") == "freqtrade-manager":
                managed.append(
                    {
                        "container_id": container.id,
                        "container_name": container.name,
                        "strategy_id": labels.get("strategy_id"),
                        "status": container.status,
                        "image": container.attrs.get("Config", {}).get("Image"),
                    }
                )

        return managed

    def get_container_port(self, strategy_id: str) -> Optional[int]:
        container_name = self._get_container_name(strategy_id)

        try:
            container = self.client.containers.get(container_name)
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})

            for container_port, host_ports in ports.items():
                if container_port == "8080/tcp" and host_ports:
                    return int(host_ports[0]["HostPort"])

            return None
        except docker.errors.NotFound:
            return None
