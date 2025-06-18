import json
import logging
from urllib.parse import urlparse

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError
from django.conf import settings

from oauth2_provider.models import Application
from oauth2_provider.settings import oauth2_settings

logger = logging.getLogger(__name__)

# Default settings for Dynamic Client Registration
DCR_SETTINGS = getattr(settings, 'OAUTH_DCR_SETTINGS', {})

# Default allowed grant types for open registration (RFC 7591 safe defaults)
DEFAULT_ALLOWED_GRANT_TYPES = [
    "authorization_code",
    "implicit",  # Part of RFC 7591, though deprecated in OAuth 2.1
    "refresh_token",  # Safe - used with other grant types for token renewal
]

# Get allowed grant types from settings
ALLOWED_GRANT_TYPES = DCR_SETTINGS.get('ALLOWED_GRANT_TYPES', DEFAULT_ALLOWED_GRANT_TYPES)

# Whether to require HTTPS for redirect URIs in production
REQUIRE_HTTPS_REDIRECT_URIS = DCR_SETTINGS.get('REQUIRE_HTTPS_REDIRECT_URIS', not settings.DEBUG)

DEFAULT_ALLOWED_TOKEN_ENDPOINT_AUTH_METHODS = [
    "none",
    "client_secret_basic",
    "client_secret_post",
]

ALLOWED_TOKEN_ENDPOINT_AUTH_METHODS = DCR_SETTINGS.get('ALLOWED_TOKEN_ENDPOINT_AUTH_METHODS', DEFAULT_ALLOWED_TOKEN_ENDPOINT_AUTH_METHODS)


@method_decorator(csrf_exempt, name='dispatch')
class DynamicClientRegistrationView(View):
    """
    OAuth 2.0 Dynamic Client Registration endpoint (RFC 7591)
    Supports "open" mode - no authentication required for registration
    """

    # Supported grant types mapping (RFC 7591 compliant)
    GRANT_TYPE_MAPPING = {
        "authorization_code": Application.GRANT_AUTHORIZATION_CODE,
        "implicit": Application.GRANT_IMPLICIT,
        "password": Application.GRANT_PASSWORD,
        "client_credentials": Application.GRANT_CLIENT_CREDENTIALS,
        "refresh_token": Application.GRANT_AUTHORIZATION_CODE,  # Refresh tokens work with auth code flow
        "urn:ietf:params:oauth:grant-type:jwt-bearer": Application.GRANT_CLIENT_CREDENTIALS,
        "urn:ietf:params:oauth:grant-type:saml2-bearer": Application.GRANT_CLIENT_CREDENTIALS,
    }

    # Supported response types mapping
    RESPONSE_TYPE_MAPPING = {
        "code": Application.GRANT_AUTHORIZATION_CODE,
        "token": Application.GRANT_IMPLICIT,
        "id_token": Application.GRANT_OPENID_HYBRID,
        "code id_token": Application.GRANT_OPENID_HYBRID,
        "code token": Application.GRANT_OPENID_HYBRID,
        "id_token token": Application.GRANT_OPENID_HYBRID,
        "code id_token token": Application.GRANT_OPENID_HYBRID,
    }

    def post(self, request):
        """Handle client registration request"""
        try:
            # Parse JSON request
            try:
                client_metadata = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                return self._error_response("invalid_client_metadata",
                                            "Invalid JSON in request body", 400)

            # Validate and process client metadata
            try:
                processed_metadata = self._validate_client_metadata(client_metadata)
            except ValidationError as e:
                return self._error_response("invalid_client_metadata",
                                            str(e), 400)

            # Create the application
            try:
                application = self._create_application(processed_metadata)
            except Exception as e:
                logger.exception(f"Failed to create application: {e}")
                return self._error_response("server_error",
                                            "Failed to register client", 500)

            # Return client information response
            return self._success_response(application, processed_metadata["token_endpoint_auth_method"])

        except Exception as e:
            logger.exception(f"Unexpected error in client registration: {e}")
            return self._error_response("server_error",
                                        "Internal server error", 500)

    def _validate_client_metadata(self, metadata):
        """Validate client metadata according to RFC 7591"""
        processed = {}

        # Client name (optional but recommended)
        if "client_name" in metadata:
            if not isinstance(metadata["client_name"], str):
                raise ValidationError("client_name must be a string")
            processed["name"] = metadata["client_name"][:255]  # Truncate if too long

        # Redirect URIs - required for certain grant types
        redirect_uris = metadata.get("redirect_uris", [])
        if redirect_uris:
            if not isinstance(redirect_uris, list):
                raise ValidationError("redirect_uris must be an array")

            # Validate each URI
            validated_uris = []
            for uri in redirect_uris:
                if not isinstance(uri, str):
                    raise ValidationError("Each redirect_uri must be a string")

                # Basic URI validation
                try:
                    parsed = urlparse(uri)
                    if not parsed.scheme or not parsed.netloc:
                        raise ValidationError(f"Invalid redirect_uri: {uri}")

                    # Check against allowed schemes
                    allowed_schemes = oauth2_settings.ALLOWED_REDIRECT_URI_SCHEMES
                    if parsed.scheme.lower() not in [s.lower() for s in allowed_schemes]:
                        raise ValidationError(f"Redirect URI scheme not allowed: {parsed.scheme}")

                    # In production, enforce HTTPS for security
                    if REQUIRE_HTTPS_REDIRECT_URIS and parsed.scheme.lower() != 'https':
                        if parsed.hostname not in ['localhost', '127.0.0.1', '::1']:
                            raise ValidationError(f"HTTPS required for redirect URIs in production: {uri}")

                    validated_uris.append(uri)
                except Exception as e:
                    logger.exception(f"Invalid redirect URI: {uri}")
                    raise ValidationError(f"Invalid redirect_uri: {uri}")

            processed["redirect_uris"] = " ".join(validated_uris)

        # Grant types
        grant_types = metadata.get("grant_types", ["authorization_code"])
        if not isinstance(grant_types, list):
            raise ValidationError("grant_types must be an array")

        # Check against allowed grant types
        for grant_type in grant_types:
            if grant_type not in ALLOWED_GRANT_TYPES:
                raise ValidationError(f"Grant type '{grant_type}' is not allowed for dynamic registration")

        # Map and validate grant types
        mapped_grants = []
        for grant_type in grant_types:
            if grant_type not in self.GRANT_TYPE_MAPPING:
                raise ValidationError(f"Unsupported grant_type: {grant_type}")
            mapped_grants.append(self.GRANT_TYPE_MAPPING[grant_type])

        # For simplicity, we'll use the first grant type as the primary one
        # In a more sophisticated implementation, you might want to store multiple grant types
        processed["authorization_grant_type"] = mapped_grants[0]

        # Response types (optional, derived from grant types if not specified)
        response_types = metadata.get("response_types")
        if response_types:
            if not isinstance(response_types, list):
                raise ValidationError("response_types must be an array")

            # Validate response types are consistent with grant types
            for response_type in response_types:
                if response_type not in self.RESPONSE_TYPE_MAPPING:
                    raise ValidationError(f"Unsupported response_type: {response_type}")

        # Client type - determine based on grant types and other factors
        if "client_credentials" in grant_types:
            processed["client_type"] = Application.CLIENT_CONFIDENTIAL
        elif "implicit" in grant_types:
            processed["client_type"] = Application.CLIENT_PUBLIC
        else:
            # Default to confidential for authorization_code
            processed["client_type"] = Application.CLIENT_CONFIDENTIAL

        # Token endpoint auth method
        token_endpoint_auth_method = processed["token_endpoint_auth_method"] = metadata.get("token_endpoint_auth_method", "client_secret_basic")
        if token_endpoint_auth_method not in ALLOWED_TOKEN_ENDPOINT_AUTH_METHODS:
            raise ValidationError(f"Unsupported token_endpoint_auth_method: {token_endpoint_auth_method}")
        if token_endpoint_auth_method == "none":
            processed["client_type"] = Application.CLIENT_PUBLIC

        # Scope (optional)
        scope = metadata.get("scope")
        if scope:
            if not isinstance(scope, str):
                raise ValidationError("scope must be a string")
            # Store scope in a custom field or handle as needed
            # The base Application model doesn't have a scope field

        # Validate redirect URIs are required for certain grant types
        auth_code_grants = [
            Application.GRANT_AUTHORIZATION_CODE,
            Application.GRANT_IMPLICIT,
            Application.GRANT_OPENID_HYBRID
        ]

        if (processed["authorization_grant_type"] in auth_code_grants and
                not processed.get("redirect_uris")):
            raise ValidationError("redirect_uris required for authorization code and implicit grants")

        # Client URI (optional)
        if "client_uri" in metadata:
            if not isinstance(metadata["client_uri"], str):
                raise ValidationError("client_uri must be a string")
            # Could store this in a custom field if needed

        # Contacts (optional)
        if "contacts" in metadata:
            if not isinstance(metadata["contacts"], list):
                raise ValidationError("contacts must be an array")

        return processed

    def _create_application(self, metadata):
        """Create Application instance from validated metadata"""
        application = Application.objects.create(
            name=metadata.get("name", ""),
            client_type=metadata["client_type"],
            authorization_grant_type=metadata["authorization_grant_type"],
            redirect_uris=metadata.get("redirect_uris", ""),
            # client_id and client_secret are auto-generated
        )

        return application

    def _success_response(self, application, token_endpoint_auth_method):
        """Generate successful registration response"""
        response_data = {
            "client_id": application.client_id,
            "client_secret": application.client_secret if application.client_type == Application.CLIENT_CONFIDENTIAL else None,
            "client_id_issued_at": int(application.created.timestamp()),
            "client_name": application.name,
            "redirect_uris": application.redirect_uris.split() if application.redirect_uris else [],
            "grant_types": [self._get_grant_type_string(application.authorization_grant_type)],
            "response_types": self._get_response_types(application.authorization_grant_type),
            "token_endpoint_auth_method": token_endpoint_auth_method,
        }

        # Remove None values
        response_data = {k: v for k, v in response_data.items() if v is not None}

        return JsonResponse(response_data, status=201)

    def _get_grant_type_string(self, grant_type):
        """Convert internal grant type to RFC string"""
        reverse_mapping = {v: k for k, v in self.GRANT_TYPE_MAPPING.items()}
        # Handle refresh_token special case since it maps to GRANT_AUTHORIZATION_CODE
        if grant_type == Application.GRANT_AUTHORIZATION_CODE:
            return "authorization_code"  # Default to authorization_code for auth code grant
        return reverse_mapping.get(grant_type, "authorization_code")

    def _get_response_types(self, grant_type):
        """Get appropriate response types for grant type"""
        if grant_type == Application.GRANT_AUTHORIZATION_CODE:
            return ["code"]
        elif grant_type == Application.GRANT_IMPLICIT:
            return ["token"]
        elif grant_type == Application.GRANT_OPENID_HYBRID:
            return ["code id_token", "code token", "id_token token"]
        else:
            return []

    def _error_response(self, error_code, error_description, status_code):
        """Generate error response according to RFC 7591"""
        return JsonResponse({
            "error": error_code,
            "error_description": error_description
        }, status=status_code)


# URL configuration helper
def get_urls():
    """Helper function to get URL patterns for this view"""
    from django.urls import path

    return [
        path('register/', DynamicClientRegistrationView.as_view(), name='oauth2_register'),
    ]
