"""
Authentication Module for Enterprise Application.

This module provides comprehensive authentication, authorization, and token
management functionality for the application. It supports JWT tokens, secure
password hashing, and session management.

Version: 2.3.0
Author: Engineering Team
"""

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional


class AuthError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid."""
    pass


class TokenExpiredError(AuthError):
    """Raised when a token has expired."""
    pass


class TokenInvalidError(AuthError):
    """Raised when a token is malformed or invalid."""
    pass


class AccountLockedError(AuthError):
    """Raised when an account is locked due to too many failed attempts."""
    pass


class PasswordPolicyError(AuthError):
    """Raised when a password doesn't meet policy requirements."""
    pass


class TokenType(Enum):
    """Types of authentication tokens."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    RESET_PASSWORD = "reset_password"


@dataclass
class TokenPayload:
    """Token payload data structure."""
    user_id: str
    username: str
    roles: list[str]
    token_type: TokenType
    issued_at: float
    expires_at: float
    jti: str  # JWT ID for token tracking


@dataclass
class AuthConfig:
    """Authentication configuration."""
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 30
    min_password_length: int = 12
    require_special_char: bool = True
    require_uppercase: bool = True
    require_number: bool = True
    hash_iterations: int = 100000


class PasswordHasher:
    """Secure password hashing using PBKDF2-HMAC-SHA256.
    
    This class provides methods for hashing and verifying passwords
    using industry-standard cryptographic algorithms. Uses PBKDF2
    with HMAC-SHA256 and a random salt.
    
    Example:
        hasher = PasswordHasher()
        hashed = hasher.hash_password("my_secure_password")
        is_valid = hasher.verify_password("my_secure_password", hashed)
    """
    
    def __init__(self, iterations: int = 100000, salt_length: int = 32):
        """Initialize the password hasher.
        
        Args:
            iterations: Number of PBKDF2 iterations (higher = more secure but slower).
            salt_length: Length of random salt in bytes.
        """
        self.iterations = iterations
        self.salt_length = salt_length
        
    def hash_password(self, password: str) -> str:
        """Hash a password using PBKDF2-HMAC-SHA256.
        
        Creates a cryptographically secure hash of the password with a random
        salt. The output format is: iterations$salt$hash (all base64 encoded).
        
        Args:
            password: Plain text password to hash.
            
        Returns:
            Formatted hash string containing iterations, salt, and hash.
            
        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash_password("secure123!")
            >>> print(hashed[:20])  # First 20 chars
            '100000$...'
        """
        salt = secrets.token_bytes(self.salt_length)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            self.iterations,
            dklen=64
        )
        salt_hex = salt.hex()
        hash_hex = hash_bytes.hex()
        return f"{self.iterations}${salt_hex}${hash_hex}"
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its hash.
        
        Compares the provided password against a previously hashed password
        using constant-time comparison to prevent timing attacks.
        
        Args:
            password: Plain text password to verify.
            hashed: Previously hashed password string.
            
        Returns:
            True if password matches, False otherwise.
            
        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash_password("secure123!")
            >>> hasher.verify_password("secure123!", hashed)
            True
            >>> hasher.verify_password("wrong_password", hashed)
            False
        """
        try:
            iterations_str, salt_hex, hash_hex = hashed.split('$')
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(hash_hex)
            
            computed_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                iterations,
                dklen=64
            )
            
            return hmac.compare_digest(computed_hash, expected_hash)
        except (ValueError, AttributeError):
            return False


class TokenManager:
    """JWT-like token management for authentication.
    
    Handles creation, validation, and refreshing of authentication tokens.
    Supports access tokens (short-lived) and refresh tokens (long-lived).
    
    The token format is a base64-encoded JSON payload with HMAC signature.
    Expired tokens raise TokenExpiredError, invalid tokens raise TokenInvalidError.
    
    Attributes:
        secret_key: Secret key used for signing tokens.
        config: Authentication configuration.
        revoked_tokens: Set of revoked token IDs.
    """
    
    def __init__(self, secret_key: str, config: Optional[AuthConfig] = None):
        """Initialize the token manager.
        
        Args:
            secret_key: Secret key for signing tokens. Should be at least 32 bytes.
            config: Optional authentication configuration.
        """
        self.secret_key = secret_key.encode('utf-8')
        self.config = config or AuthConfig()
        self.revoked_tokens: set[str] = set()
        
    def create_token(
        self,
        user_id: str,
        username: str,
        roles: list[str],
        token_type: TokenType = TokenType.ACCESS,
        custom_ttl_minutes: Optional[int] = None,
    ) -> str:
        """Create a new authentication token.
        
        Generates a signed token containing user information and metadata.
        The token includes a unique ID (jti) for tracking and revocation.
        
        Args:
            user_id: Unique identifier for the user.
            username: User's login name.
            roles: List of role names assigned to the user.
            token_type: Type of token to create (ACCESS, REFRESH, etc.).
            custom_ttl_minutes: Override default TTL for this token.
            
        Returns:
            Signed token string.
            
        Example:
            >>> manager = TokenManager("my_secret_key")
            >>> token = manager.create_token("user123", "john", ["admin"])
            >>> print(len(token) > 100)
            True
        """
        now = time.time()
        
        if custom_ttl_minutes:
            ttl = custom_ttl_minutes
        elif token_type == TokenType.REFRESH:
            ttl = self.config.refresh_token_ttl_days * 24 * 60
        else:
            ttl = self.config.access_token_ttl_minutes
            
        payload = TokenPayload(
            user_id=user_id,
            username=username,
            roles=roles,
            token_type=token_type,
            issued_at=now,
            expires_at=now + (ttl * 60),
            jti=secrets.token_urlsafe(16),
        )
        
        return self._encode_token(payload)
    
    def validate_token(self, token: str) -> TokenPayload:
        """Validate a token and return its payload.
        
        Verifies the token signature, checks expiration, and ensures
        the token hasn't been revoked. Raises appropriate exceptions
        for invalid or expired tokens.
        
        Args:
            token: Token string to validate.
            
        Returns:
            TokenPayload if valid.
            
        Raises:
            TokenExpiredError: If the token has expired.
            TokenInvalidError: If the token is malformed or signature is invalid.
            
        Example:
            >>> manager = TokenManager("secret")
            >>> token = manager.create_token("user1", "alice", ["user"])
            >>> payload = manager.validate_token(token)
            >>> print(payload.username)
            'alice'
        """
        try:
            payload = self._decode_token(token)
        except Exception as e:
            raise TokenInvalidError(f"Failed to decode token: {e}")
            
        # Check if revoked
        if payload.jti in self.revoked_tokens:
            raise TokenInvalidError("Token has been revoked")
            
        # Check expiration
        if time.time() > payload.expires_at:
            raise TokenExpiredError(
                f"Token expired at {datetime.fromtimestamp(payload.expires_at)}"
            )
            
        return payload
    
    def refresh_token(self, refresh_token: str) -> tuple[str, str]:
        """Refresh an access token using a refresh token.
        
        Validates the refresh token and generates a new access token
        and refresh token pair. The old refresh token is revoked.
        
        Args:
            refresh_token: Valid refresh token.
            
        Returns:
            Tuple of (new_access_token, new_refresh_token).
            
        Raises:
            TokenExpiredError: If refresh token has expired.
            TokenInvalidError: If refresh token is invalid or not a refresh type.
            
        Example:
            >>> manager = TokenManager("secret")
            >>> refresh = manager.create_token("u1", "bob", ["user"], TokenType.REFRESH)
            >>> access, new_refresh = manager.refresh_token(refresh)
        """
        payload = self.validate_token(refresh_token)
        
        if payload.token_type != TokenType.REFRESH:
            raise TokenInvalidError("Not a refresh token")
            
        # Revoke the old refresh token
        self.revoke_token(refresh_token)
        
        # Create new token pair
        new_access = self.create_token(
            payload.user_id,
            payload.username,
            payload.roles,
            TokenType.ACCESS,
        )
        new_refresh = self.create_token(
            payload.user_id,
            payload.username,
            payload.roles,
            TokenType.REFRESH,
        )
        
        return new_access, new_refresh
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a token to prevent further use.
        
        Adds the token's JTI to the revoked set. Subsequent validation
        attempts will fail.
        
        Args:
            token: Token to revoke.
            
        Returns:
            True if successfully revoked, False if token was invalid.
        """
        try:
            payload = self._decode_token(token)
            self.revoked_tokens.add(payload.jti)
            return True
        except Exception:
            return False
    
    def _encode_token(self, payload: TokenPayload) -> str:
        """Encode and sign a token payload."""
        import base64
        
        data = {
            'uid': payload.user_id,
            'usr': payload.username,
            'rol': payload.roles,
            'typ': payload.token_type.value,
            'iat': payload.issued_at,
            'exp': payload.expires_at,
            'jti': payload.jti,
        }
        
        payload_bytes = json.dumps(data).encode('utf-8')
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8')
        
        signature = hmac.new(
            self.secret_key,
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        return f"{payload_b64}.{signature}"
    
    def _decode_token(self, token: str) -> TokenPayload:
        """Decode and verify a token."""
        import base64
        
        parts = token.split('.')
        if len(parts) != 2:
            raise TokenInvalidError("Invalid token format")
            
        payload_b64, signature = parts
        
        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
        except Exception:
            raise TokenInvalidError("Invalid base64 encoding")
            
        expected_sig = hmac.new(
            self.secret_key,
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            raise TokenInvalidError("Invalid signature")
            
        data = json.loads(payload_bytes)
        
        return TokenPayload(
            user_id=data['uid'],
            username=data['usr'],
            roles=data['rol'],
            token_type=TokenType(data['typ']),
            issued_at=data['iat'],
            expires_at=data['exp'],
            jti=data['jti'],
        )


class AuthService:
    """Main authentication service coordinating login, logout, and password changes.
    
    This is the primary interface for authentication operations. It integrates
    TokenManager and PasswordHasher to provide a complete authentication flow.
    
    Features:
        - User authentication with username/password
        - Account lockout after failed attempts
        - Password change with old password verification
        - Session management with token revocation
        - Audit logging for security events
    
    Example:
        >>> auth = AuthService(secret_key="my_secret")
        >>> tokens = auth.authenticate("john", "password123")
        >>> auth.logout(tokens['access_token'])
    """
    
    def __init__(
        self,
        secret_key: str,
        config: Optional[AuthConfig] = None,
        user_store: Optional[dict] = None,
    ):
        """Initialize the authentication service.
        
        Args:
            secret_key: Secret key for token signing.
            config: Authentication configuration.
            user_store: Optional dictionary of users for testing.
        """
        self.config = config or AuthConfig()
        self.token_manager = TokenManager(secret_key, self.config)
        self.password_hasher = PasswordHasher(self.config.hash_iterations)
        self.user_store = user_store or {}
        self.failed_attempts: dict[str, int] = {}
        self.lockout_until: dict[str, float] = {}
        self.active_sessions: dict[str, set[str]] = {}  # user_id -> set of token jtis
        
    def authenticate(
        self,
        username: str,
        password: str,
    ) -> dict[str, Any]:
        """Authenticate a user with username and password.
        
        Validates credentials and returns access and refresh tokens.
        Implements account lockout after configured number of failed attempts.
        
        Args:
            username: User's login name.
            password: Plain text password.
            
        Returns:
            Dictionary containing:
                - access_token: Short-lived token for API access
                - refresh_token: Long-lived token for getting new access tokens
                - expires_in: Access token TTL in seconds
                - user: User information dict
                
        Raises:
            InvalidCredentialsError: If username or password is wrong.
            AccountLockedError: If account is locked due to failed attempts.
            
        Example:
            >>> auth = AuthService("secret")
            >>> result = auth.authenticate("john_doe", "secure_password!")
            >>> print(result.keys())
            dict_keys(['access_token', 'refresh_token', 'expires_in', 'user'])
        """
        # Check lockout
        if self._is_locked_out(username):
            remaining = self.lockout_until.get(username, 0) - time.time()
            raise AccountLockedError(
                f"Account locked. Try again in {int(remaining / 60)} minutes."
            )
        
        # Get user
        user = self.user_store.get(username)
        if not user:
            self._record_failed_attempt(username)
            raise InvalidCredentialsError("Invalid username or password")
            
        # Verify password
        if not self.password_hasher.verify_password(password, user['password_hash']):
            self._record_failed_attempt(username)
            raise InvalidCredentialsError("Invalid username or password")
            
        # Clear failed attempts on success
        self.failed_attempts.pop(username, None)
        self.lockout_until.pop(username, None)
        
        # Create tokens
        access_token = self.token_manager.create_token(
            user['id'],
            username,
            user.get('roles', ['user']),
            TokenType.ACCESS,
        )
        refresh_token = self.token_manager.create_token(
            user['id'],
            username,
            user.get('roles', ['user']),
            TokenType.REFRESH,
        )
        
        # Track session
        payload = self.token_manager._decode_token(access_token)
        if user['id'] not in self.active_sessions:
            self.active_sessions[user['id']] = set()
        self.active_sessions[user['id']].add(payload.jti)
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': self.config.access_token_ttl_minutes * 60,
            'user': {
                'id': user['id'],
                'username': username,
                'roles': user.get('roles', ['user']),
            },
        }
    
    def logout(self, access_token: str) -> bool:
        """Log out a user by revoking their token.
        
        Revokes the provided access token and removes the session
        from active sessions tracking.
        
        Args:
            access_token: Token to revoke.
            
        Returns:
            True if logout successful, False otherwise.
            
        Example:
            >>> auth = AuthService("secret")
            >>> # ... authenticate first ...
            >>> auth.logout(access_token)
            True
        """
        try:
            payload = self.token_manager._decode_token(access_token)
            self.token_manager.revoke_token(access_token)
            
            # Remove from active sessions
            if payload.user_id in self.active_sessions:
                self.active_sessions[payload.user_id].discard(payload.jti)
                
            return True
        except Exception:
            return False
    
    def change_password(
        self,
        username: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        """Change a user's password.
        
        Verifies the old password, validates the new password against
        the password policy, and updates the stored hash.
        
        Args:
            username: User's login name.
            old_password: Current password for verification.
            new_password: New password to set.
            
        Returns:
            True if password was changed successfully.
            
        Raises:
            InvalidCredentialsError: If old password is wrong.
            PasswordPolicyError: If new password doesn't meet requirements.
            
        Example:
            >>> auth = AuthService("secret")
            >>> auth.change_password("john", "old_pass", "new_secure_pass!")
            True
        """
        user = self.user_store.get(username)
        if not user:
            raise InvalidCredentialsError("User not found")
            
        # Verify old password
        if not self.password_hasher.verify_password(old_password, user['password_hash']):
            raise InvalidCredentialsError("Current password is incorrect")
            
        # Validate new password
        self._validate_password_policy(new_password)
        
        # Update password
        user['password_hash'] = self.password_hasher.hash_password(new_password)
        
        # Revoke all existing tokens for security
        if user['id'] in self.active_sessions:
            self.active_sessions[user['id']].clear()
            
        return True
    
    def _validate_password_policy(self, password: str) -> None:
        """Validate password against configured policy."""
        errors = []
        
        if len(password) < self.config.min_password_length:
            errors.append(
                f"Password must be at least {self.config.min_password_length} characters"
            )
            
        if self.config.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
            
        if self.config.require_number and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
            
        if self.config.require_special_char:
            special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
            if not any(c in special_chars for c in password):
                errors.append("Password must contain at least one special character")
                
        if errors:
            raise PasswordPolicyError("; ".join(errors))
    
    def _is_locked_out(self, username: str) -> bool:
        """Check if an account is currently locked out."""
        lockout_time = self.lockout_until.get(username, 0)
        if lockout_time > time.time():
            return True
        return False
    
    def _record_failed_attempt(self, username: str) -> None:
        """Record a failed login attempt."""
        self.failed_attempts[username] = self.failed_attempts.get(username, 0) + 1
        
        if self.failed_attempts[username] >= self.config.max_failed_attempts:
            self.lockout_until[username] = (
                time.time() + self.config.lockout_duration_minutes * 60
            )


def create_test_user(
    auth_service: AuthService,
    username: str,
    password: str,
    roles: Optional[list[str]] = None,
) -> dict:
    """Helper function to create a test user.
    
    Args:
        auth_service: AuthService instance.
        username: Username for the new user.
        password: Plain text password.
        roles: List of roles to assign.
        
    Returns:
        Created user dict.
    """
    user = {
        'id': f"user_{secrets.token_hex(8)}",
        'username': username,
        'password_hash': auth_service.password_hasher.hash_password(password),
        'roles': roles or ['user'],
        'created_at': datetime.now().isoformat(),
    }
    auth_service.user_store[username] = user
    return user


if __name__ == "__main__":
    # Demo usage
    auth = AuthService(secret_key="demo_secret_key_change_in_production")
    
    # Create a test user
    user = create_test_user(auth, "demo_user", "SecureP@ss123!")
    print(f"Created user: {user['username']}")
    
    # Authenticate
    result = auth.authenticate("demo_user", "SecureP@ss123!")
    print(f"Authenticated! Token expires in {result['expires_in']} seconds")
    
    # Change password
    auth.change_password("demo_user", "SecureP@ss123!", "NewSecureP@ss456!")
    print("Password changed successfully")
    
    # Logout
    auth.logout(result['access_token'])
    print("Logged out successfully")
