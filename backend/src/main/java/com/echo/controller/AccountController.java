package com.echo.controller;

import com.echo.dto.Dtos.AddWatchlistItemRequest;
import com.echo.dto.Dtos.AlertDto;
import com.echo.dto.Dtos.ApiKeyDto;
import com.echo.dto.Dtos.CheckoutRequest;
import com.echo.dto.Dtos.CheckoutResponse;
import com.echo.dto.Dtos.CreateApiKeyRequest;
import com.echo.dto.Dtos.CreateWatchlistRequest;
import com.echo.dto.Dtos.CreatedApiKeyDto;
import com.echo.dto.Dtos.PlanDto;
import com.echo.dto.Dtos.WatchlistDto;
import com.echo.exception.ApiException;
import com.echo.model.Plan;
import com.echo.security.CurrentUser;
import com.echo.service.AccountService;
import com.echo.service.WatchlistService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@Tag(name = "Account", description = "Watchlists, alerts, plans/billing and API keys of the signed-in user")
public class AccountController {

    private final WatchlistService watchlists;
    private final AccountService account;

    public AccountController(WatchlistService watchlists, AccountService account) {
        this.watchlists = watchlists;
        this.account = account;
    }

    // ---------------------------------------------------------------- watchlists
    @GetMapping("/watchlists")
    public List<WatchlistDto> watchlists() {
        return watchlists.list(CurrentUser.require());
    }

    @PostMapping("/watchlists")
    @ResponseStatus(HttpStatus.CREATED)
    public WatchlistDto createWatchlist(@Valid @RequestBody CreateWatchlistRequest req) {
        return watchlists.create(CurrentUser.require(), req.name());
    }

    @DeleteMapping("/watchlists/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteWatchlist(@PathVariable Long id) {
        watchlists.delete(CurrentUser.require(), id);
    }

    @PostMapping("/watchlists/{id}/items")
    @Operation(summary = "Add (or update the alert threshold of) a company on a watchlist")
    public WatchlistDto addItem(@PathVariable Long id, @Valid @RequestBody AddWatchlistItemRequest req) {
        if (req.companyId() == null) {
            throw ApiException.badRequest("companyId is required");
        }
        return watchlists.addItem(CurrentUser.require(), id, req.companyId(), req.scoreDropThreshold());
    }

    @DeleteMapping("/watchlists/{id}/items/{companyId}")
    public WatchlistDto removeItem(@PathVariable Long id, @PathVariable Long companyId) {
        return watchlists.removeItem(CurrentUser.require(), id, companyId);
    }

    // ---------------------------------------------------------------- alerts
    @GetMapping("/alerts")
    public List<AlertDto> alerts() {
        return account.alerts(CurrentUser.require());
    }

    @PatchMapping("/alerts/{id}/read")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void markRead(@PathVariable Long id) {
        account.markAlertRead(CurrentUser.require(), id);
    }

    @PostMapping("/alerts/read-all")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void markAllRead() {
        account.markAllAlertsRead(CurrentUser.require());
    }

    // ---------------------------------------------------------------- billing
    @GetMapping("/billing/plans")
    @Operation(summary = "Plan catalogue with prices and limits")
    public List<PlanDto> plans() {
        return Arrays.stream(Plan.values()).map(PlanDto::of).toList();
    }

    @PostMapping("/billing/checkout")
    @Operation(summary = "Change plan (demo billing mode activates immediately without payment)")
    public CheckoutResponse checkout(@Valid @RequestBody CheckoutRequest req) {
        return account.checkout(CurrentUser.require(), req.plan());
    }

    // ---------------------------------------------------------------- API keys
    @GetMapping("/me/api-keys")
    public List<ApiKeyDto> apiKeys() {
        return account.apiKeys(CurrentUser.require());
    }

    @PostMapping("/me/api-keys")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Create an API key (Pro/Enterprise); the secret is returned only once")
    public CreatedApiKeyDto createApiKey(@Valid @RequestBody CreateApiKeyRequest req) {
        return account.createApiKey(CurrentUser.require(), req.name());
    }

    @DeleteMapping("/me/api-keys/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void revokeApiKey(@PathVariable Long id) {
        account.revokeApiKey(CurrentUser.require(), id);
    }
}
