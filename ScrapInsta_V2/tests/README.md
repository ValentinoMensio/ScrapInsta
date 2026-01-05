# Tests de ScrapInsta V2

Esta carpeta contiene todos los tests del proyecto. Los tests están diseñados para **NO usar servicios reales** (BD, Selenium, OpenAI, etc.), usando mocks en su lugar.

## Estructura

```
tests/
├── __init__.py
├── conftest.py              # Fixtures compartidas y configuración
├── README.md                # Este archivo
├── unit/                    # Tests unitarios
│   ├── __init__.py
│   ├── test_evaluator.py
│   ├── test_analyze_profile_usecase.py
│   └── test_fetch_followings_usecase.py
└── integration/             # Tests de integración (futuro)
    └── __init__.py
```

## Ejecutar Tests

### Todos los tests

```bash
pytest
```

### Tests específicos

```bash
# Un archivo
pytest tests/unit/test_evaluator.py

# Una clase de tests
pytest tests/unit/test_evaluator.py::TestEngagementBenchmark

# Un test específico
pytest tests/unit/test_evaluator.py::TestEngagementBenchmark::test_engagement_benchmark_small_account
```

### Con cobertura

```bash
pytest --cov=src/scrapinsta --cov-report=html
```

El reporte HTML se genera en `htmlcov/index.html`.

### Verbose

```bash
pytest -v
```

### Solo tests que fallaron anteriormente

```bash
pytest --lf
```

## Fixtures Disponibles

### Mocks de Repositorios

- `mock_profile_repo`: Mock de `ProfileRepository`
- `mock_followings_repo`: Mock de `FollowingsRepo`
- `mock_job_store`: Mock de `JobStorePort`

### Mocks de Servicios Externos

- `mock_browser_port`: Mock de `BrowserPort` (Selenium)
- `mock_openai_client`: Mock de cliente OpenAI
- `mock_message_sender`: Mock de `MessageSenderPort`
- `mock_message_composer`: Mock de `MessageComposerPort`

### Configuración

- `test_settings`: Configuración de test
- `disable_external_calls`: Fixture automática que previene llamadas reales

## Convenciones

1. **Nunca usar servicios reales**: Todos los tests deben usar mocks
2. **Nombres descriptivos**: Los nombres de tests deben ser claros
3. **Un test, un concepto**: Cada test debe probar una cosa
4. **Arrange-Act-Assert**: Estructura clara de los tests
5. **Fixtures compartidas**: Usar fixtures de `conftest.py` cuando sea posible

## Ejemplo de Test

```python
def test_analyze_profile_success(
    mock_browser_port: Mock,
    mock_profile_repo: Mock,
):
    """Test de análisis exitoso de perfil."""
    # Arrange
    use_case = AnalyzeProfileUseCase(
        browser=mock_browser_port,
        profile_repo=mock_profile_repo,
    )
    request = AnalyzeProfileRequest(username="testuser")
    
    # Act
    response = use_case(request)
    
    # Assert
    assert response.snapshot is not None
    mock_browser_port.get_profile_snapshot.assert_called_once()
```

## Dependencias de Testing

Las dependencias de testing están en `requirements.txt`:
- `pytest`: Framework de testing
- `pytest-cov`: Cobertura de código
- `pytest-mock`: Mocks mejorados
- `httpx`: Para tests de FastAPI (TestClient)

## Notas Importantes

⚠️ **Los tests NO deben:**
- Conectarse a bases de datos reales
- Ejecutar Selenium/Chrome
- Hacer llamadas HTTP reales
- Usar API keys reales
- Modificar datos de producción

✅ **Los tests SÍ deben:**
- Usar mocks para todas las dependencias externas
- Ser rápidos (segundos, no minutos)
- Ser determinísticos (mismo resultado siempre)
- Probar comportamientos, no implementaciones

