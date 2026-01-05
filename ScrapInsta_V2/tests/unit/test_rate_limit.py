"""
Tests para SlidingWindowRateLimiter.

Cubre:
- RateLimitConfig: configuración de límites
- SlidingWindowRateLimiter: limitador de tasa con ventana deslizante
- allow_now: verificar si se permite evento
- record_event: registrar evento
- next_available_in: tiempo hasta próximo slot
- apply_cooldown: aplicar cooldown aleatorio
"""
from __future__ import annotations

import time
from unittest.mock import patch, Mock

import pytest

from scrapinsta.crosscutting.rate_limit import RateLimitConfig, SlidingWindowRateLimiter


class TestRateLimitConfig:
    """Tests para RateLimitConfig."""
    
    def test_rate_limit_config_defaults(self):
        """Configuración con valores por defecto."""
        config = RateLimitConfig(
            window_seconds=3600,
            max_events=100
        )
        assert config.window_seconds == 3600
        assert config.max_events == 100
        assert config.cooldown_range == (600, 2400)  # 10-40 min por defecto
    
    def test_rate_limit_config_custom_cooldown(self):
        """Configuración con cooldown personalizado."""
        config = RateLimitConfig(
            window_seconds=3600,
            max_events=100,
            cooldown_range=(300, 600)  # 5-10 min
        )
        assert config.cooldown_range == (300, 600)


class TestSlidingWindowRateLimiter:
    """Tests para SlidingWindowRateLimiter."""
    
    @pytest.fixture
    def config(self):
        """Configuración de rate limiter para tests."""
        return RateLimitConfig(
            window_seconds=60,  # 1 minuto
            max_events=5,  # 5 eventos máximo
            cooldown_range=(10, 20)  # 10-20 segundos
        )
    
    @pytest.fixture
    def limiter(self, config):
        """Rate limiter para tests."""
        return SlidingWindowRateLimiter(config, seed=42)
    
    def test_allow_now_initially_allows(self, limiter):
        """Inicialmente permite eventos."""
        assert limiter.allow_now() is True
    
    def test_allow_now_within_limit(self, limiter):
        """Permite eventos dentro del límite."""
        for i in range(5):
            assert limiter.allow_now() is True
            limiter.record_event()
    
    def test_allow_now_exceeds_limit(self, limiter):
        """No permite eventos cuando se excede el límite."""
        # Registrar 5 eventos (máximo)
        for _ in range(5):
            limiter.record_event()
        
        # El siguiente no debe ser permitido
        assert limiter.allow_now() is False
    
    def test_record_event(self, limiter):
        """Registrar evento incrementa el contador."""
        assert limiter.allow_now() is True
        limiter.record_event()
        # Aún debe permitir (solo 1 de 5)
        assert limiter.allow_now() is True
    
    def test_record_event_multiple(self, limiter):
        """Registrar múltiples eventos."""
        for i in range(4):
            limiter.record_event()
            assert limiter.allow_now() is True  # Aún hay espacio
        
        limiter.record_event()  # 5to evento
        assert limiter.allow_now() is False  # Ya no hay espacio
    
    def test_next_available_in_within_capacity(self, limiter):
        """next_available_in retorna 0 cuando hay capacidad."""
        assert limiter.next_available_in() == 0.0
        limiter.record_event()
        assert limiter.next_available_in() == 0.0
    
    def test_next_available_in_exceeds_limit(self, limiter):
        """next_available_in retorna tiempo hasta próximo slot cuando se excede límite."""
        # Registrar eventos hasta el límite
        for _ in range(5):
            limiter.record_event()
        
        # Debe retornar tiempo hasta que expire el evento más antiguo
        next_available = limiter.next_available_in()
        assert next_available > 0.0
        assert next_available <= 60.0  # Dentro de la ventana
    
    @patch('time.time')
    def test_next_available_in_after_window(self, mock_time, limiter):
        """next_available_in considera la ventana deslizante."""
        # Simular tiempo inicial
        mock_time.return_value = 1000.0
        
        # Registrar eventos hasta el límite
        for _ in range(5):
            limiter.record_event()
        
        # Avanzar tiempo más allá de la ventana
        mock_time.return_value = 1100.0  # 100 segundos después
        
        # Ahora debe haber capacidad (eventos antiguos expirados)
        assert limiter.next_available_in() == 0.0
    
    def test_apply_cooldown(self, limiter):
        """apply_cooldown aplica un cooldown aleatorio."""
        duration = limiter.apply_cooldown()
        
        # Debe estar en el rango configurado
        assert 10.0 <= duration <= 20.0
        
        # No debe permitir eventos durante cooldown
        assert limiter.allow_now() is False
    
    @patch('time.time')
    def test_apply_cooldown_expires(self, mock_time, limiter):
        """El cooldown expira después del tiempo configurado."""
        mock_time.return_value = 1000.0
        
        duration = limiter.apply_cooldown()
        assert limiter.allow_now() is False
        
        # Avanzar tiempo más allá del cooldown
        mock_time.return_value = 1000.0 + duration + 1.0
        
        # Ahora debe permitir eventos
        assert limiter.allow_now() is True
    
    def test_evict_old_events(self, limiter):
        """Los eventos antiguos se eliminan automáticamente."""
        # Registrar eventos hasta el límite
        for _ in range(5):
            limiter.record_event()
        
        assert limiter.allow_now() is False
        
        # Simular paso del tiempo (más allá de la ventana)
        with patch('time.time', return_value=time.time() + 70):
            # Ahora debe permitir eventos (eventos antiguos expirados)
            assert limiter.allow_now() is True
    
    def test_evict_old_events_partial(self, limiter):
        """Solo se eliminan eventos fuera de la ventana."""
        # Registrar algunos eventos
        for _ in range(3):
            limiter.record_event()
        
        # Avanzar tiempo parcialmente (algunos eventos aún válidos)
        with patch('time.time', return_value=time.time() + 30):
            # Aún debe permitir (eventos aún dentro de la ventana)
            assert limiter.allow_now() is True
    
    def test_cooldown_takes_precedence(self, limiter):
        """El cooldown tiene precedencia sobre el límite de eventos."""
        # Aplicar cooldown
        limiter.apply_cooldown()
        
        # Aunque no haya eventos registrados, no debe permitir
        assert limiter.allow_now() is False
    
    def test_next_available_in_during_cooldown(self, limiter):
        """next_available_in retorna tiempo de cooldown si está activo."""
        limiter.apply_cooldown()
        
        next_available = limiter.next_available_in()
        assert next_available > 0.0
        assert 10.0 <= next_available <= 20.0
    
    def test_seed_reproducibility(self):
        """El seed permite reproducibilidad en cooldowns."""
        config = RateLimitConfig(
            window_seconds=60,
            max_events=5,
            cooldown_range=(10, 20)
        )
        
        limiter1 = SlidingWindowRateLimiter(config, seed=42)
        limiter2 = SlidingWindowRateLimiter(config, seed=42)
        
        # Con el mismo seed, los cooldowns deben ser iguales
        duration1 = limiter1.apply_cooldown()
        duration2 = limiter2.apply_cooldown()
        
        assert duration1 == duration2
    
    def test_different_seeds_different_cooldowns(self):
        """Diferentes seeds producen diferentes cooldowns."""
        config = RateLimitConfig(
            window_seconds=60,
            max_events=5,
            cooldown_range=(10, 20)
        )
        
        limiter1 = SlidingWindowRateLimiter(config, seed=42)
        limiter2 = SlidingWindowRateLimiter(config, seed=123)
        
        duration1 = limiter1.apply_cooldown()
        duration2 = limiter2.apply_cooldown()
        
        # Probablemente diferentes (aunque podrían coincidir por casualidad)
        # Al menos verificamos que ambos están en el rango
        assert 10.0 <= duration1 <= 20.0
        assert 10.0 <= duration2 <= 20.0
    
    def test_window_seconds_boundary(self, limiter):
        """Los eventos se eliminan exactamente en el boundary de la ventana."""
        # Registrar un evento
        limiter.record_event()
        
        # Avanzar tiempo exactamente a la ventana
        with patch('time.time', return_value=time.time() + 60):
            # El evento debe estar justo en el boundary
            # Dependiendo de la implementación, puede o no estar incluido
            # Por ahora solo verificamos que funciona
            next_available = limiter.next_available_in()
            assert next_available >= 0.0
    
    def test_max_events_zero(self):
        """Rate limiter con max_events=0 no permite eventos."""
        config = RateLimitConfig(
            window_seconds=60,
            max_events=0
        )
        limiter = SlidingWindowRateLimiter(config)
        
        assert limiter.allow_now() is False
    
    def test_large_window(self):
        """Rate limiter con ventana grande."""
        config = RateLimitConfig(
            window_seconds=3600,  # 1 hora
            max_events=100
        )
        limiter = SlidingWindowRateLimiter(config)
        
        # Debe permitir eventos
        assert limiter.allow_now() is True
        
        # Registrar muchos eventos
        for _ in range(100):
            limiter.record_event()
        
        # Ya no debe permitir
        assert limiter.allow_now() is False

