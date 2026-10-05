package com.echo.controller;

import com.echo.dto.Dtos.AuthResponse;
import com.echo.dto.Dtos.LoginRequest;
import com.echo.dto.Dtos.MeDto;
import com.echo.dto.Dtos.RegisterRequest;
import com.echo.security.CurrentUser;
import com.echo.service.AccountService;
import com.echo.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
@Tag(name = "Auth", description = "Registration, login (JWT) and the current account")
public class AuthController {

    private final AuthService auth;
    private final AccountService account;

    public AuthController(AuthService auth, AccountService account) {
        this.auth = auth;
        this.account = account;
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Create an account (Free plan) and return an access token")
    public AuthResponse register(@Valid @RequestBody RegisterRequest req) {
        return auth.register(req);
    }

    @PostMapping("/login")
    @Operation(summary = "Exchange email + password for a JWT access token")
    public AuthResponse login(@Valid @RequestBody LoginRequest req) {
        return auth.login(req);
    }

    @GetMapping("/me")
    @Operation(summary = "Current user, plan limits, today's usage and unread alerts")
    public MeDto me() {
        return account.me(CurrentUser.require());
    }
}
