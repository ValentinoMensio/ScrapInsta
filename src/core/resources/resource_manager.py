from collections import deque
import time
from typing import Dict, Optional, Tuple
import uuid

class ResourceManager:
    def __init__(self, total_workers):
        self.worker_capacity = {i: 1.0 for i in range(total_workers)}  # Capacidad de 0 a 1
        self.performance_metrics = {
            i: {
                'tasks_completed': 0,
                'total_processing_time': 0,
                'last_10_tasks': deque(maxlen=10),
                'current_requests': set()  # IDs de requests activos
            } for i in range(total_workers)
        }
        self.MAX_CAPACITY_PERCENTAGE = 0.8  # 80% de capacidad máxima
        self.MIN_CAPACITY_PERCENTAGE = 0.2  # 20% de capacidad mínima
        self.BASE_PROCESSING_TIME = 30  # Tiempo base de procesamiento en segundos
        self.active_requests: Dict[str, Dict] = {}  # Registro de requests activos

    def update_capacity(self, worker_id: int, task_duration: float, request_id: str):
        """Actualiza la capacidad del worker basado en su rendimiento"""
        metrics = self.performance_metrics[worker_id]
        metrics['tasks_completed'] += 1
        metrics['total_processing_time'] += task_duration
        metrics['last_10_tasks'].append(task_duration)
        
        # Liberar el request del worker
        if request_id in metrics['current_requests']:
            metrics['current_requests'].remove(request_id)
            self.worker_capacity[worker_id] += self.active_requests[request_id]['required_capacity']
            del self.active_requests[request_id]
        
        if len(metrics['last_10_tasks']) > 0:
            avg_time = sum(metrics['last_10_tasks']) / len(metrics['last_10_tasks'])
            # Ajustar capacidad según rendimiento
            self.worker_capacity[worker_id] = min(
                self.MAX_CAPACITY_PERCENTAGE,
                max(self.MIN_CAPACITY_PERCENTAGE, self.BASE_PROCESSING_TIME / avg_time)
            )

    def get_available_capacity(self) -> float:
        """Calcula la capacidad disponible total"""
        return sum(self.worker_capacity.values())

    def assign_task(self, task_size: int, priority: int) -> Tuple[Optional[int], str]:
        """Asigna una tarea al worker más adecuado"""
        request_id = str(uuid.uuid4())
        required_capacity = task_size / 100  # Normalizar a porcentaje
        
        # Verificar si hay suficiente capacidad total
        if required_capacity > self.get_available_capacity():
            return None, "Capacidad insuficiente"

        # Encontrar el mejor worker disponible
        best_worker = None
        best_score = float('-inf')
        
        for worker_id, capacity in self.worker_capacity.items():
            if capacity >= required_capacity:
                metrics = self.performance_metrics[worker_id]
                avg_time = (sum(metrics['last_10_tasks']) / len(metrics['last_10_tasks'])) if metrics['last_10_tasks'] else self.BASE_PROCESSING_TIME
                
                # Penalizar workers con muchas requests activas
                active_requests_penalty = len(metrics['current_requests']) * 0.1
                
                # Calcular score considerando:
                # 1. Capacidad disponible
                # 2. Rendimiento histórico
                # 3. Penalización por requests activas
                # 4. Prioridad de la tarea
                score = (capacity / required_capacity) * \
                       (self.BASE_PROCESSING_TIME / avg_time) * \
                       (1 - active_requests_penalty) * \
                       (priority * 0.2)  # Aumentar score para prioridades más altas
                
                if score > best_score:
                    best_score = score
                    best_worker = worker_id

        if best_worker is not None:
            # Actualizar capacidad y registrar la request
            self.worker_capacity[best_worker] -= required_capacity
            self.performance_metrics[best_worker]['current_requests'].add(request_id)
            self.active_requests[request_id] = {
                'worker_id': best_worker,
                'required_capacity': required_capacity,
                'priority': priority,
                'task_size': task_size,
                'start_time': time.time()
            }
            return best_worker, request_id

        return None, "No se encontró worker adecuado"

    def get_worker_status(self, worker_id: int) -> Dict:
        """Obtiene el estado actual de un worker"""
        metrics = self.performance_metrics[worker_id]
        avg_time = (sum(metrics['last_10_tasks']) / len(metrics['last_10_tasks'])) if metrics['last_10_tasks'] else self.BASE_PROCESSING_TIME
        
        return {
            "current_capacity": self.worker_capacity[worker_id],
            "active_requests": len(metrics['current_requests']),
            "performance": {
                "tasks_completed": metrics['tasks_completed'],
                "average_processing_time": avg_time
            }
        }

    def get_system_status(self) -> Dict:
        """Obtiene el estado general del sistema"""
        total_capacity = self.get_available_capacity()
        active_requests = len(self.active_requests)
        
        # Calcular carga promedio por worker
        worker_loads = {}
        for worker_id in self.worker_capacity:
            metrics = self.performance_metrics[worker_id]
            worker_loads[worker_id] = {
                "current_capacity": self.worker_capacity[worker_id],
                "active_requests": len(metrics['current_requests']),
                "average_processing_time": sum(metrics['last_10_tasks']) / len(metrics['last_10_tasks']) if metrics['last_10_tasks'] else 0,
                "tasks_completed": metrics['tasks_completed']
            }
        
        return {
            "total_capacity": total_capacity,
            "active_requests": active_requests,
            "workers": worker_loads,
            "system_load": {
                "total_requests": active_requests,
                "average_load_per_worker": sum(1 - w["current_capacity"] for w in worker_loads.values()) / len(worker_loads),
                "most_loaded_worker": max(worker_loads.items(), key=lambda x: len(x[1]["active_requests"]))[0]
            }
        }

# Instancia global del ResourceManager
resource_manager = None 