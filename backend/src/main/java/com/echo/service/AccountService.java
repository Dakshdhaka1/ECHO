package com.echo.service;

import com.echo.config.EchoProperties;
import com.echo.dto.Dtos.AlertDto;
import com.echo.dto.Dtos.ApiKeyDto;
import com.echo.dto.Dtos.CheckoutResponse;
import com.echo.dto.Dtos.CreatedApiKeyDto;
import com.echo.dto.Dtos.MeDto;
import com.echo.dto.Dtos.PlanDto;
import com.echo.dto.Dtos.UserDto;
import com.echo.exception.ApiException;
import com.echo.model.ApiKey;
import com.echo.model.Plan;
import com.echo.model.User;
import com.echo.repository.AlertRepository;
import com.echo.repository.ApiKeyRepository;
import com.echo.security.ApiKeyHasher;
import java.util.List;
import java.util.Locale;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** The signed-in user's account: profile + usage, plan changes (billing), API keys and alert inbox. */
@Service
public class AccountService {

    private final PlanService plans;
    private final ApiKeyRepository keys;
    private final AlertRepository alerts;
    private final EchoProperties props;

    public AccountService(PlanService plans, ApiKeyRepository keys, AlertRepository alerts, EchoProperties props) {
        this.plans = plans;
        this.keys = keys;
        this.alerts = alerts;
        this.props = props;
    }

    @Transactional(readOnly = true)
    public MeDto me(Long userId) {
        User u = plans.user(userId);
        return new MeDto(UserDto.of(u), PlanDto.of(u.getPlan()), plans.usageToday(userId),
                alerts.countByUserIdAndReadAtIsNull(userId));
    }

    /**
     * Plan change. In {@code demo} billing mode the plan is activated immediately and no payment is taken; a
     * payment provider (e.g. Stripe Checkout + webhook) would replace this method in production.
     */
    @Transactional
    public CheckoutResponse checkout(Long userId, String planName) {
        Plan plan;
        try {
            plan = Plan.valueOf(planName.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw ApiException.badRequest("Unknown plan " + planName);
        }
        if (!"demo".equalsIgnoreCase(props.billing().mode())) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "billing-not-configured",
                    "No payment provider is configured for this deployment.");
        }
        User u = plans.user(userId);
        u.changePlan(plan);
        if (plan.maxApiKeys() == 0) {
            keys.findByUserIdOrderByCreatedAtDesc(userId).forEach(ApiKey::revoke);
        }
        return new CheckoutResponse(UserDto.of(u), "demo",
                "Demo billing: " + plan.label() + " activated without payment.");
    }

    @Transactional(readOnly = true)
    public List<ApiKeyDto> apiKeys(Long userId) {
        return keys.findByUserIdOrderByCreatedAtDesc(userId).stream().map(ApiKeyDto::of).toList();
    }

    @Transactional
    public CreatedApiKeyDto createApiKey(Long userId, String name) {
        Plan plan = plans.planOf(userId);
        if (plan.maxApiKeys() == 0) {
            throw ApiException.planLimit("API access is part of the Pro and Enterprise plans.");
        }
        if (keys.countByUserIdAndRevokedAtIsNull(userId) >= plan.maxApiKeys()) {
            throw ApiException.planLimit("The " + plan.label() + " plan allows " + plan.maxApiKeys() + " active API keys.");
        }
        String raw = ApiKeyHasher.newKey();
        ApiKey key = keys.save(new ApiKey(userId, name.trim(), raw.substring(0, 12), ApiKeyHasher.sha256(raw)));
        return new CreatedApiKeyDto(ApiKeyDto.of(key), raw);
    }

    @Transactional
    public void revokeApiKey(Long userId, Long keyId) {
        keys.findByIdAndUserId(keyId, userId).orElseThrow(() -> ApiException.notFound("API key")).revoke();
    }

    @Transactional(readOnly = true)
    public List<AlertDto> alerts(Long userId) {
        return alerts.findTop100ByUserIdOrderByCreatedAtDesc(userId).stream().map(AlertDto::of).toList();
    }

    @Transactional
    public void markAlertRead(Long userId, Long alertId) {
        alerts.findByIdAndUserId(alertId, userId).orElseThrow(() -> ApiException.notFound("alert")).markRead();
    }

    @Transactional
    public void markAllAlertsRead(Long userId) {
        alerts.findTop100ByUserIdOrderByCreatedAtDesc(userId).forEach(a -> a.markRead());
    }
}
