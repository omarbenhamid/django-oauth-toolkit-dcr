
# Django OAuth Toolkit DCR

[![PyPI version](https://img.shields.io/pypi/v/django-oauth-toolkit-dcr)](https://pypi.org/project/django-oauth-toolkit-dcr/)
![License](https://img.shields.io/pypi/l/django-oauth-toolkit-dcr)
[![Published on Django Packages](https://img.shields.io/badge/Published%20on-Django%20Packages-0c3c26)](https://djangopackages.org/packages/p/django-oauth-toolkit-dcr/)
![Python versions](https://img.shields.io/pypi/pyversions/django-oauth-toolkit-dcr)
[![Django versions](https://img.shields.io/pypi/frameworkversions/django/django-oauth-toolkit-dcr)](https://pypi.org/project/django-oauth-toolkit-dcr/)

An extension to [Django OAuth Toolkit](https://github.com/jazzband/django-oauth-toolkit) that adds support for **OAuth 2.0 Dynamic Client Registration** as defined in [RFC 7591](https://tools.ietf.org/html/rfc7591).

## Features

- ✅ **RFC 7591 Compliant**: Full implementation of OAuth 2.0 Dynamic Client Registration
- ✅ **Open Registration Mode**: No authentication required for client registration
- ✅ **Comprehensive Validation**: Validates client metadata, redirect URIs, and grant types
- ✅ **Django OAuth Toolkit Integration**: Seamlessly works with existing DOT applications
- ✅ **Flexible Grant Type Support**: Authorization Code, Implicit, Client Credentials, and more
- ✅ **Error Handling**: RFC-compliant error responses
- ✅ **Security Focused**: Built-in validations and configurable restrictions

## Installation

Install the package using pip:

```bash
pip install django-oauth-toolkit-dcr
```

## Requirements

- Python 3.10+
- Django 4.0+
- django-oauth-toolkit 3.0.1+

## Quick Start

### 1. Add to Django Settings

Add the package to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... your other apps
    'oauth2_provider',
    'oauth_dcr',
]
```

### 2. Configure URLs

Add the Dynamic Client Registration endpoint to your URL configuration:

```python
# urls.py
from django.urls import path, include
from oauth_dcr.views import DynamicClientRegistrationView

urlpatterns = [
    # Your existing OAuth2 URLs
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    
    # Dynamic Client Registration endpoint
    path('o/register/', DynamicClientRegistrationView.as_view(), name='oauth2_dcr'),
]
```

### 3. Run Migrations

Make sure your Django OAuth Toolkit migrations are up to date:

```bash
python manage.py migrate
```

## Usage

### Client Registration Request

Clients can register themselves by sending a POST request to the registration endpoint:

```bash
curl -X POST https://your-server.com/o/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "My Amazing App",
    "redirect_uris": [
      "https://myapp.com/oauth/callback",
      "https://myapp.com/oauth/callback2"
    ],
    "grant_types": ["authorization_code"],
    "response_types": ["code"],
    "scope": "read write",
    "client_uri": "https://myapp.com",
    "contacts": ["admin@myapp.com"]
  }'
```

### Successful Registration Response

```json
{
  "client_id": "AbCdEf123456",
  "client_secret": "secret_AbCdEf123456789",
  "client_id_issued_at": 1625097600,
  "client_name": "My Amazing App",
  "redirect_uris": [
    "https://myapp.com/oauth/callback",
    "https://myapp.com/oauth/callback2"
  ],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

### Error Response Examples

**Invalid Grant Type:**
```json
{
  "error": "invalid_client_metadata",
  "error_description": "Grant type 'password' is not allowed for dynamic registration"
}
```

**Missing Redirect URIs:**
```json
{
  "error": "invalid_client_metadata",
  "error_description": "redirect_uris required for authorization code grants"
}
```

**HTTPS Required:**
```json
{
  "error": "invalid_client_metadata",
  "error_description": "HTTPS required for redirect URIs in production: http://example.com/callback"
}
```

## Supported Client Metadata

The following client metadata parameters are supported:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `client_name` | No | Human-readable name for the client |
| `redirect_uris` | Conditional* | Array of redirect URIs |
| `grant_types` | No | Array of grant types (default: `["authorization_code"]`) |
| `response_types` | No | Array of response types |
| `scope` | No | Space-separated list of scopes |
| `client_uri` | No | URL of the client's homepage |
| `contacts` | No | Array of contact email addresses |
| `token_endpoint_auth_method` | No | Token endpoint authentication method |

*Required for `authorization_code`, `implicit`, and hybrid flows.

## Supported Grant Types

- `authorization_code` - Authorization Code Grant
- `implicit` - Implicit Grant  
- `password` - Resource Owner Password Credentials Grant
- `client_credentials` - Client Credentials Grant
- `urn:ietf:params:oauth:grant-type:jwt-bearer` - JWT Bearer Grant

## Configuration

### Django OAuth Toolkit Settings

The extension respects your existing Django OAuth Toolkit configuration:

```python
# settings.py
OAUTH2_PROVIDER = {
    'ALLOWED_REDIRECT_URI_SCHEMES': ['https', 'http'],  # Used for validation
    'OIDC_RSA_PRIVATE_KEY': 'your-rsa-key',  # For OIDC support
    # ... other settings
}
```

### Dynamic Client Registration Settings

Configure DCR-specific settings for enhanced security:

```python
# settings.py
OAUTH_DCR_SETTINGS = {
    # Grant types allowed for dynamic registration (security-focused defaults)
    'ALLOWED_GRANT_TYPES': [
        'authorization_code',  # Safe for open registration
        # 'implicit',          # Deprecated in OAuth 2.1, uncomment if needed
        # 'password',          # SECURITY RISK: Allows credential collection
        # 'client_credentials', # SECURITY RISK: Machine-to-machine access
        # 'urn:ietf:params:oauth:grant-type:jwt-bearer',  # SECURITY RISK
    ],
    
    # Require HTTPS for redirect URIs in production (default: True in production)
    'REQUIRE_HTTPS_REDIRECT_URIS': True,
}
```

#### Security Rationale for Grant Type Restrictions

| Grant Type | Security Risk | Why Restricted by Default |
|------------|---------------|---------------------------|
| `password` | **HIGH** | Allows any client to collect user credentials |
| `client_credentials` | **HIGH** | Enables machine-to-machine access without user consent |
| `jwt-bearer` | **MEDIUM** | Can potentially bypass normal authentication flows |
| `implicit` | **MEDIUM** | Deprecated due to token exposure in URL |
| `authorization_code` | **LOW** | Secure with proper PKCE implementation |

### Security Considerations

Since this implements "open" registration mode, the following security measures are **strongly recommended**:

1. **Grant Type Restrictions**: Only allow safe grant types (default configuration)
2. **HTTPS Enforcement**: Require HTTPS for redirect URIs in production (default)
3. **Rate Limiting**: Use Django rate limiting middleware
4. **Monitoring**: Log all registration attempts
5. **Cleanup**: Implement periodic cleanup of unused clients
6. **Network Security**: Consider IP allowlisting or VPN requirements

## Advanced Usage

### Custom Validation

You can extend the view to add custom validation:

```python
from oauth_dcr.views import DynamicClientRegistrationView
from django.core.exceptions import ValidationError

class CustomDCRView(DynamicClientRegistrationView):
    def _validate_client_metadata(self, metadata):
        # Call parent validation first
        processed = super()._validate_client_metadata(metadata)
        
        # Add custom validation
        if 'client_name' in metadata:
            if 'forbidden' in metadata['client_name'].lower():
                raise ValidationError("Client name contains forbidden words")
        
        return processed
```

### Rate Limiting Example

Using django-ratelimit:

```python
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

@method_decorator(ratelimit(key='ip', rate='10/h', method='POST'), name='post')
class RateLimitedDCRView(DynamicClientRegistrationView):
    pass
```

## API Reference

### DynamicClientRegistrationView

Main view class that handles client registration requests.

#### Methods

- `post(request)` - Handle registration requests
- `_validate_client_metadata(metadata)` - Override for custom validation
- `_create_application(metadata)` - Override for custom application creation

## Testing

Run the tests:

```bash
pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Projects

- [Django OAuth Toolkit](https://github.com/jazzband/django-oauth-toolkit) - The base OAuth 2.0 implementation
- [oauthlib](https://github.com/oauthlib/oauthlib) - The underlying OAuth library

## Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/omarbenhamid/django-oauth-toolkit-dcr/issues) page
2. Create a new issue with detailed information
3. For general OAuth questions, refer to the [Django OAuth Toolkit documentation](https://django-oauth-toolkit.readthedocs.io/)

## Changelog

### v0.1.0 (Initial Release)

- Initial implementation of RFC 7591 Dynamic Client Registration
- Support for open registration mode
- Comprehensive client metadata validation
- Integration with Django OAuth Toolkit Application model