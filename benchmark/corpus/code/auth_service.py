"""
Authentication Service Module

This module provides authentication and authorization services for the application.
It handles user login, token management, and permission validation.

Author: TechCorp Engineering Team
Version: 2.1.0
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import json
import base64


class AuthError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid."""
    pass


class TokenExpiredError(AuthError):
    """Raised when authentication token has expired."""
    pass


class PermissionDeniedError(AuthError):
    """Raised when user lacks required permissions."""
    pass


class UserRole(Enum):
    """User role enumeration for RBAC."""
    GUEST = "guest"
    USER = "user"
    EDITOR = "editor"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


@dataclass
class User:
    """Represents an authenticated user."""
    user_id: str
    email: str
    username: str
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    permissions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        if self.role == UserRole.SUPER_ADMIN:
            return True
        return permission in self.permissions

    def has_role(self, required_role: UserRole) -> bool:
        """Check if user's role meets the required level."""
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.EDITOR: 2,
            UserRole.ADMIN: 3,
            UserRole.SUPER_ADMIN: 4
        }
        return role_hierarchy[self.role] >= role_hierarchy[required_role]


@dataclass
class AuthToken:
    """JWT-like authentication token."""
    token_id: str
    user_id: str
    issued_at: datetime
    expires_at: datetime
    refresh_token: Optional[str] = None
    scopes: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if the token has expired."""
        return datetime.utcnow() > self.expires_at

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until token expires."""
        return self.expires_at - datetime.utcnow()


class PasswordHasher:
    """Secure password hashing utility using PBKDF2."""
    
    ALGORITHM = 'sha256'
    ITERATIONS = 100_000
    SALT_LENGTH = 32
    HASH_LENGTH = 64

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        Hash a password with a random salt.
        
        Args:
            password: Plain text password to hash
            
        Returns:
            Base64 encoded string containing salt and hash
        """
        salt = secrets.token_bytes(cls.SALT_LENGTH)
        password_hash = hashlib.pbkdf2_hmac(
            cls.ALGORITHM,
            password.encode('utf-8'),
            salt,
            cls.ITERATIONS,
            dklen=cls.HASH_LENGTH
        )
        # Combine salt and hash, then encode
        combined = salt + password_hash
        return base64.b64encode(combined).decode('utf-8')

    @classmethod
    def verify_password(cls, password: str, stored_hash: str) -> bool:
        """
        Verify a password against a stored hash.
        
        Args:
            password: Plain text password to verify
            stored_hash: Previously hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            decoded = base64.b64decode(stored_hash.encode('utf-8'))
            salt = decoded[:cls.SALT_LENGTH]
            stored_password_hash = decoded[cls.SALT_LENGTH:]
            
            computed_hash = hashlib.pbkdf2_hmac(
                cls.ALGORITHM,
                password.encode('utf-8'),
                salt,
                cls.ITERATIONS,
                dklen=cls.HASH_LENGTH
            )
            return hmac.compare_digest(computed_hash, stored_password_hash)
        except Exception:
            return False


class TokenManager:
    """Manages authentication token lifecycle."""
    
    DEFAULT_EXPIRY_HOURS = 24
    REFRESH_TOKEN_DAYS = 30
    
    def __init__(self, secret_key: str):
        """
        Initialize TokenManager with a secret key.
        
        Args:
            secret_key: Secret key for signing tokens
        """
        self.secret_key = secret_key
        self._tokens: dict[str, AuthToken] = {}

    def create_token(
        self,
        user_id: str,
        scopes: list[str] = None,
        expiry_hours: int = None
    ) -> AuthToken:
        """
        Create a new authentication token for a user.
        
        Args:
            user_id: ID of the user to create token for
            scopes: Optional list of permission scopes
            expiry_hours: Hours until token expires
            
        Returns:
            New AuthToken instance
        """
        token_id = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        now = datetime.utcnow()
        
        expiry = expiry_hours or self.DEFAULT_EXPIRY_HOURS
        
        token = AuthToken(
            token_id=token_id,
            user_id=user_id,
            issued_at=now,
            expires_at=now + timedelta(hours=expiry),
            refresh_token=refresh_token,
            scopes=scopes or []
        )
        
        self._tokens[token_id] = token
        return token

    def validate_token(self, token_id: str) -> AuthToken:
        """
        Validate and return an authentication token.
        
        Args:
            token_id: Token ID to validate
            
        Returns:
            Valid AuthToken instance
            
        Raises:
            InvalidCredentialsError: If token doesn't exist
            TokenExpiredError: If token has expired
        """
        token = self._tokens.get(token_id)
        if not token:
            raise InvalidCredentialsError("Invalid token")
        
        if token.is_expired():
            del self._tokens[token_id]
            raise TokenExpiredError("Token has expired")
        
        return token

    def refresh_token(self, refresh_token: str) -> AuthToken:
        """
        Create a new token using a refresh token.
        
        Args:
            refresh_token: Refresh token string
            
        Returns:
            New AuthToken instance
            
        Raises:
            InvalidCredentialsError: If refresh token is invalid
        """
        for token in self._tokens.values():
            if token.refresh_token == refresh_token:
                # Create new token with same user and scopes
                return self.create_token(token.user_id, token.scopes)
        
        raise InvalidCredentialsError("Invalid refresh token")

    def revoke_token(self, token_id: str) -> bool:
        """
        Revoke an authentication token.
        
        Args:
            token_id: Token ID to revoke
            
        Returns:
            True if token was revoked, False if not found
        """
        if token_id in self._tokens:
            del self._tokens[token_id]
            return True
        return False

    def cleanup_expired_tokens(self) -> int:
        """
        Remove all expired tokens from storage.
        
        Returns:
            Number of tokens removed
        """
        expired = [
            tid for tid, token in self._tokens.items()
            if token.is_expired()
        ]
        for tid in expired:
            del self._tokens[tid]
        return len(expired)


class AuthService:
    """
    Main authentication service.
    
    Handles user authentication, token management, and authorization.
    """
    
    def __init__(self, secret_key: str, user_store: dict = None):
        """
        Initialize AuthService.
        
        Args:
            secret_key: Secret key for token signing
            user_store: Optional dict mapping user_id to User objects
        """
        self.token_manager = TokenManager(secret_key)
        self.password_hasher = PasswordHasher()
        self._users: dict[str, tuple[User, str]] = user_store or {}  # user_id -> (User, password_hash)

    def register_user(
        self,
        email: str,
        username: str,
        password: str,
        role: UserRole = UserRole.USER
    ) -> User:
        """
        Register a new user.
        
        Args:
            email: User's email address
            username: User's username
            password: Plain text password
            role: User's role (default: USER)
            
        Returns:
            Newly created User object
        """
        user_id = secrets.token_urlsafe(16)
        password_hash = self.password_hasher.hash_password(password)
        
        user = User(
            user_id=user_id,
            email=email,
            username=username,
            role=role,
            created_at=datetime.utcnow()
        )
        
        self._users[user_id] = (user, password_hash)
        return user

    def authenticate(self, email: str, password: str) -> tuple[User, AuthToken]:
        """
        Authenticate a user with email and password.
        
        Args:
            email: User's email
            password: User's password
            
        Returns:
            Tuple of (User, AuthToken)
            
        Raises:
            InvalidCredentialsError: If authentication fails
        """
        # Find user by email
        for user_id, (user, password_hash) in self._users.items():
            if user.email == email:
                if not user.is_active:
                    raise InvalidCredentialsError("Account is disabled")
                
                if self.password_hasher.verify_password(password, password_hash):
                    # Update last login
                    user.last_login = datetime.utcnow()
                    # Create token
                    token = self.token_manager.create_token(user_id)
                    return user, token
        
        raise InvalidCredentialsError("Invalid email or password")

    def authorize(
        self,
        token_id: str,
        required_permission: str = None,
        required_role: UserRole = None
    ) -> User:
        """
        Authorize a request using a token.
        
        Args:
            token_id: Authentication token ID
            required_permission: Optional permission to check
            required_role: Optional minimum role required
            
        Returns:
            Authorized User object
            
        Raises:
            InvalidCredentialsError: If token is invalid
            TokenExpiredError: If token has expired
            PermissionDeniedError: If authorization fails
        """
        token = self.token_manager.validate_token(token_id)
        
        user_data = self._users.get(token.user_id)
        if not user_data:
            raise InvalidCredentialsError("User not found")
        
        user, _ = user_data
        
        if required_permission and not user.has_permission(required_permission):
            raise PermissionDeniedError(f"Missing permission: {required_permission}")
        
        if required_role and not user.has_role(required_role):
            raise PermissionDeniedError(f"Insufficient role: requires {required_role.value}")
        
        return user

    def logout(self, token_id: str) -> bool:
        """
        Log out a user by revoking their token.
        
        Args:
            token_id: Token to revoke
            
        Returns:
            True if logout successful
        """
        return self.token_manager.revoke_token(token_id)

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """
        Change a user's password.
        
        Args:
            user_id: User's ID
            old_password: Current password
            new_password: New password
            
        Returns:
            True if password changed successfully
            
        Raises:
            InvalidCredentialsError: If old password is wrong
        """
        user_data = self._users.get(user_id)
        if not user_data:
            raise InvalidCredentialsError("User not found")
        
        user, old_hash = user_data
        
        if not self.password_hasher.verify_password(old_password, old_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        
        new_hash = self.password_hasher.hash_password(new_password)
        self._users[user_id] = (user, new_hash)
        return True


# Decorator for protecting routes/functions
def require_auth(permission: str = None, role: UserRole = None):
    """
    Decorator to require authentication for a function.
    
    Args:
        permission: Optional permission required
        role: Optional minimum role required
    """
    def decorator(func):
        def wrapper(auth_service: AuthService, token_id: str, *args, **kwargs):
            user = auth_service.authorize(token_id, permission, role)
            return func(user, *args, **kwargs)
        return wrapper
    return decorator


# Example usage
if __name__ == "__main__":
    # Initialize service
    auth = AuthService(secret_key="your-secret-key-here")
    
    # Register a user
    user = auth.register_user(
        email="alice@example.com",
        username="alice",
        password="securepassword123",
        role=UserRole.ADMIN
    )
    print(f"Registered user: {user.username} ({user.role.value})")
    
    # Authenticate
    user, token = auth.authenticate("alice@example.com", "securepassword123")
    print(f"Authenticated! Token expires: {token.expires_at}")
    
    # Authorize a request
    authorized_user = auth.authorize(token.token_id, required_role=UserRole.USER)
    print(f"Authorized: {authorized_user.username}")
    
    # Logout
    auth.logout(token.token_id)
    print("Logged out successfully")
