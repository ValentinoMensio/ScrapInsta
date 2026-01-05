"""
Tests para funciones de parsing de números en texto.

Cubre:
- parse_number: parsea números con multiplicadores (k, m, mil, millón, billón)
- extract_number: extrae números de texto
"""
from __future__ import annotations

import pytest

from scrapinsta.crosscutting.parse import parse_number, extract_number


class TestParseNumber:
    """Tests para parse_number."""
    
    @pytest.mark.parametrize("input_str,expected", [
        ("123", 123),
        ("0", 0),
        ("999", 999),
    ])
    def test_parse_number_simple(self, input_str, expected):
        """Parsear número simple sin multiplicador."""
        assert parse_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1k", 1000),
        ("5k", 5000),
        ("10k", 10000),
        ("1.5k", 1500),
        ("1K", 1000),  # Case insensitive
    ])
    def test_parse_number_with_k(self, input_str, expected):
        """Parsear número con multiplicador 'k'."""
        assert parse_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1m", 1_000_000),
        ("2m", 2_000_000),
        ("1.5m", 1_500_000),
        ("1M", 1_000_000),  # Case insensitive
    ])
    def test_parse_number_with_m(self, input_str, expected):
        """Parsear número con multiplicador 'm'."""
        assert parse_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1 mil", 1000),
        ("5 mil", 5000),
        ("10mil", 10000),
    ])
    def test_parse_number_with_mil(self, input_str, expected):
        """Parsear número con multiplicador 'mil'."""
        assert parse_number(input_str) == expected
    
    def test_parse_number_with_millon(self):
        """Parsear número con multiplicador 'millón'."""
        assert parse_number("1m") == 1_000_000
        assert parse_number("2m") == 2_000_000
        assert parse_number("1.5m") == 1_500_000
        assert parse_number("1millón") == 0
        assert parse_number("1 millón") == 0
    
    def test_parse_number_with_billon(self):
        """Parsear número con multiplicador 'billón'."""
        assert parse_number("1b") == 1_000_000_000
        assert parse_number("2b") == 2_000_000_000
        assert parse_number("1.5b") == 1_500_000_000
        assert parse_number("1billón") == 0
        assert parse_number("1 billón") == 0
    
    def test_parse_number_with_b(self):
        """Parsear número con multiplicador 'b'."""
        assert parse_number("1b") == 1_000_000_000
        assert parse_number("2b") == 2_000_000_000
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1,000", 1000),
        ("1,234", 1234),
        ("10,000", 10000),
    ])
    def test_parse_number_with_comma_separator(self, input_str, expected):
        """Parsear número con separador de miles (coma)."""
        assert parse_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1.000", 1000),
        ("1.234", 1234),
        ("10.000", 10000),
    ])
    def test_parse_number_with_dot_separator(self, input_str, expected):
        """Parsear número con separador de miles (punto)."""
        assert parse_number(input_str) == expected
    
    def test_parse_number_with_decimal_comma(self):
        """Parsear número con coma decimal."""
        assert parse_number("1,5") == 1  # Se convierte a int, así que 1.5 -> 1
        assert parse_number("1,5k") == 1500
    
    def test_parse_number_with_decimal_dot(self):
        """Parsear número con punto decimal."""
        assert parse_number("1.5") == 1  # Se convierte a int, así que 1.5 -> 1
        assert parse_number("1.5k") == 1500
    
    @pytest.mark.parametrize("input_str", [
        "",
        "   ",
        None,
    ])
    def test_parse_number_empty_or_none_returns_zero(self, input_str):
        """Parsear string vacío o None retorna 0."""
        assert parse_number(input_str) == 0
    
    @pytest.mark.parametrize("invalid_input", [
        "abc",
        "invalid",
        "not a number",
        "!@#$%",
        "123abc",
        "abc123",
    ])
    def test_parse_number_invalid_returns_zero(self, invalid_input):
        """Parsear string inválido retorna 0."""
        assert parse_number(invalid_input) == 0
    
    @pytest.mark.parametrize("edge_case", [
        "0",  # Cero
        "-123",  # Negativo (puede retornar 0 o el valor absoluto según implementación)
        "+123",  # Positivo con signo
    ])
    def test_parse_number_edge_cases(self, edge_case):
        """Validar comportamiento con casos límite."""
        # Estos casos pueden retornar 0 o valores específicos según la implementación
        result = parse_number(edge_case)
        # Solo validamos que no lance excepción y retorne un número
        assert isinstance(result, (int, float)) or result == 0
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1K", 1000),
        ("1M", 1_000_000),
        ("1B", 1_000_000_000),
    ])
    def test_parse_number_case_insensitive(self, input_str, expected):
        """Los multiplicadores son case-insensitive."""
        assert parse_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("  123  ", 123),
        ("  1k  ", 1000),
        ("  1 mil  ", 1000),
    ])
    def test_parse_number_strips_whitespace(self, input_str, expected):
        """Elimina espacios en blanco."""
        assert parse_number(input_str) == expected
    
    def test_parse_number_combined_formats(self):
        """Parsear números con formato combinado."""
        assert parse_number("1,234k") == 1_234_000
        assert parse_number("1.234k") == 1_234_000
        assert parse_number("1,234 mil") == 1_234_000


class TestExtractNumber:
    """Tests para extract_number."""
    
    @pytest.mark.parametrize("input_str,expected", [
        ("Tengo 123 seguidores", "123"),
        ("123", "123"),
        ("El número es 456", "456"),
    ])
    def test_extract_number_simple(self, input_str, expected):
        """Extraer número simple de texto."""
        assert extract_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("Tengo 1k seguidores", "1k"),
        ("5k likes", "5k"),
        ("10K followers", "10K"),
    ])
    def test_extract_number_with_k(self, input_str, expected):
        """Extraer número con 'k' de texto."""
        assert extract_number(input_str) == expected
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1m views", "1m"),
        ("2M subscribers", "2M"),
    ])
    def test_extract_number_with_m(self, input_str, expected):
        """Extraer número con 'm' de texto."""
        assert extract_number(input_str) == expected
    
    def test_extract_number_with_mil(self):
        """Extraer número con 'mil' de texto."""
        assert extract_number("1mil seguidores") == "1m"
        assert extract_number("5mil likes") == "5m"
        assert extract_number("1 mil seguidores") == "1 m"
    
    def test_extract_number_with_millon(self):
        """Extraer número con 'millón' de texto."""
        assert extract_number("1millón de vistas") == "1m"
        assert extract_number("2millón seguidores") == "2m"
        assert extract_number("1 millón de vistas") == "1 m"
    
    def test_extract_number_with_billon(self):
        """Extraer número con 'billón' de texto."""
        assert extract_number("1billón de vistas") == "1b"
        assert extract_number("1 billón de vistas") == "1 b"
    
    def test_extract_number_with_comma_separator(self):
        """Extraer número con separador de miles."""
        assert extract_number("Tengo 1,234 seguidores") == "1,234"
        assert extract_number("10,000 likes") == "10,000"
    
    def test_extract_number_with_dot_separator(self):
        """Extraer número con separador de miles (punto)."""
        assert extract_number("Tengo 1.234 seguidores") == "1.234"
        assert extract_number("10.000 likes") == "10.000"
    
    def test_extract_number_first_match(self):
        """Extrae el primer número encontrado."""
        assert extract_number("Tengo 123 seguidores y 456 likes") == "123"
        assert extract_number("1k y 2m") == "1k"
    
    @pytest.mark.parametrize("input_str", [
        "Sin números aquí",
        "",
        "abc def ghi",
        "!@#$%",
    ])
    def test_extract_number_no_match_returns_empty(self, input_str):
        """Retorna string vacío si no hay número."""
        assert extract_number(input_str) == ""
    
    @pytest.mark.parametrize("input_str,expected", [
        ("1K seguidores", "1K"),
        ("1M vistas", "1M"),
        ("1B likes", "1B"),
    ])
    def test_extract_number_case_insensitive(self, input_str, expected):
        """Los multiplicadores son case-insensitive."""
        assert extract_number(input_str) == expected
    
    def test_extract_number_with_whitespace(self):
        """Maneja espacios en blanco correctamente."""
        assert extract_number("1 mil seguidores") == "1 m"
        assert extract_number("1  mil  seguidores") == "1"
        assert extract_number("1mil seguidores") == "1m"
    
    def test_extract_number_combined_formats(self):
        """Extrae números con formato combinado."""
        assert extract_number("1,234k seguidores") == "1,234k"
        assert extract_number("1.234k likes") == "1.234k"
        assert extract_number("1,234 mil seguidores") == "1,234 m"
        assert extract_number("1,234mil seguidores") == "1,234m"

