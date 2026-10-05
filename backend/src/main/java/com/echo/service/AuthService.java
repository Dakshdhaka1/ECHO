package com.echo.service;

import com.echo.dto.Dtos.AuthResponse;
import com.echo.dto.Dtos.LoginRequest;
import com.echo.dto.Dtos.RegisterRequest;
import com.echo.dto.Dtos.UserDto;
import com.echo.exception.ApiException;
import com.echo.model.User;
import com.echo.repository.UserRepository;
import com.echo.security.TokenService;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final TokenService tokens;
    private final Set<String> adminEmails;

    public AuthService(UserRepository users, PasswordEncoder encoder, TokenService tokens,
                       @Value("${echo.admin-emails:}") String adminEmails) {
        this.users = users;
        this.encoder = encoder;
        this.tokens = tokens;
        this.adminEmails = Arrays.stream(adminEmails.split(",")).map(s -> s.trim().toLowerCase(Locale.ROOT))
                .filter(s -> !s.isEmpty()).collect(Collectors.toSet());
    }

    @Transactional
    public AuthResponse register(RegisterRequest req) {
        String email = req.email().trim().toLowerCase(Locale.ROOT);
        if (users.existsByEmailIgnoreCase(email)) {
            throw ApiException.conflict("An account with this email already exists.");
        }
        String name = req.displayName() == null || req.displayName().isBlank() ? email.split("@")[0] : req.displayName().trim();
        User user = new User(email, encoder.encode(req.password()), name);
        if (adminEmails.contains(email)) {
            user.setRole(User.Role.ADMIN);
        }
        users.save(user);
        return respond(user);
    }

    @Transactional(readOnly = true)
    public AuthResponse login(LoginRequest req) {
        User user = users.findByEmailIgnoreCase(req.email().trim())
                .filter(u -> encoder.matches(req.password(), u.getPasswordHash()))
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "invalid-credentials",
                        "Email or password is incorrect."));
        return respond(user);
    }

    private AuthResponse respond(User user) {
        TokenService.IssuedToken t = tokens.issue(user);
        return new AuthResponse(t.token(), t.expiresAt(), UserDto.of(user));
    }
}
