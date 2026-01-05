"""
Tests para Value Objects del dominio.
"""
import pytest
from pydantic import ValidationError

from scrapinsta.domain.models.profile_models import Username, Following


class TestUsername:
    """Tests para el Value Object Username."""
    
    def test_username_valid(self):
        """Username válido se crea correctamente."""
        username = Username(value="testuser")
        assert username.value == "testuser"
    
    def test_username_normalizes_lowercase(self):
        """Username se normaliza a lowercase."""
        username = Username(value="TestUser")
        assert username.value == "testuser"
    
    def test_username_strips_whitespace(self):
        """Username elimina espacios en blanco."""
        username = Username(value="  testuser  ")
        assert username.value == "testuser"
    
    def test_username_removes_at_symbol(self):
        """Username elimina el símbolo @."""
        username = Username(value="@testuser")
        assert username.value == "testuser"
    
    def test_username_allows_dot_and_underscore(self):
        """Username permite punto y guión bajo."""
        username1 = Username(value="test.user")
        assert username1.value == "test.user"
        
        username2 = Username(value="test_user")
        assert username2.value == "test_user"
        
        username3 = Username(value="test.user_123")
        assert username3.value == "test.user_123"
    
    @pytest.mark.parametrize("invalid_username", [
        "",  # Vacío (menos de 1 caracter)
        "   ",  # Solo espacios (después de strip queda vacío)
        "a" * 31,  # Muy largo (más de 30 caracteres)
        "a" * 100,  # Extremadamente largo
    ])
    def test_username_invalid_length(self, invalid_username):
        """Username con longitud inválida es rechazado."""
        with pytest.raises(ValidationError):
            Username(value=invalid_username)
    
    def test_username_invalid_starts_with_dot(self):
        """Username no puede empezar con punto."""
        with pytest.raises(ValidationError) as exc_info:
            Username(value=".testuser")
        assert "empezar ni terminar con punto" in str(exc_info.value)
    
    def test_username_invalid_ends_with_dot(self):
        """Username no puede terminar con punto."""
        with pytest.raises(ValidationError) as exc_info:
            Username(value="testuser.")
        assert "empezar ni terminar con punto" in str(exc_info.value)
    
    def test_username_invalid_consecutive_dots(self):
        """Username no puede tener puntos consecutivos."""
        with pytest.raises(ValidationError) as exc_info:
            Username(value="test..user")
        assert "consecutivos" in str(exc_info.value)
    
    @pytest.mark.parametrize("invalid_username,expected_error_keyword", [
        ("test-user", "letras, números"),
        ("test@user", "letras, números"),
        ("test user", "letras, números"),
        ("test#user", "letras, números"),
        ("test$user", "letras, números"),
    ])
    def test_username_invalid_special_characters(self, invalid_username, expected_error_keyword):
        """Username no permite caracteres especiales."""
        with pytest.raises(ValidationError) as exc_info:
            Username(value=invalid_username)
        assert expected_error_keyword in str(exc_info.value)
    
    def test_username_invalid_spaces(self):
        """Username no permite espacios."""
        with pytest.raises(ValidationError) as exc_info:
            Username(value="test user")
        assert "letras, números" in str(exc_info.value)
    
    def test_username_is_frozen(self):
        """Username es inmutable."""
        username = Username(value="testuser")
        with pytest.raises(Exception):  # Pydantic frozen model
            username.value = "newuser"


class TestFollowing:
    """Tests para el Value Object Following."""
    
    def test_following_valid(self):
        """Following válido se crea correctamente."""
        owner = Username(value="owner")
        target = Username(value="target")
        following = Following(owner=owner, target=target)
        
        assert following.owner.value == "owner"
        assert following.target.value == "target"
    
    def test_following_normalizes_usernames(self):
        """Following normaliza los usernames."""
        owner = Username(value="@Owner")
        target = Username(value="  Target  ")
        following = Following(owner=owner, target=target)
        
        assert following.owner.value == "owner"
        assert following.target.value == "target"
    
    def test_following_same_owner_target_invalid(self):
        """Following NO puede tener mismo owner y target."""
        username = Username(value="sameuser")
        with pytest.raises(ValidationError) as exc_info:
            Following(owner=username, target=username)
        assert "mismo usuario" in str(exc_info.value)
    
    def test_following_is_frozen(self):
        """Following es inmutable."""
        owner = Username(value="owner")
        target = Username(value="target")
        following = Following(owner=owner, target=target)
        
        with pytest.raises(Exception):  # Pydantic frozen model
            following.owner = Username(value="newowner")

