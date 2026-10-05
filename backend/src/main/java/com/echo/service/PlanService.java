package com.echo.service;

import com.echo.dto.Dtos.UsageDto;
import com.echo.exception.ApiException;
import com.echo.model.Plan;
import com.echo.model.UsageEvent;
import com.echo.model.User;
import com.echo.repository.UsageEventRepository;
import com.echo.repository.UserRepository;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.springframework.stereotype.Service;

/** Plan limits (FREE / PRO / ENTERPRISE) and metered usage. */
@Service
public class PlanService {

    private final UserRepository users;
    private final UsageEventRepository usage;

    public PlanService(UserRepository users, UsageEventRepository usage) {
        this.users = users;
        this.usage = usage;
    }

    public User user(Long userId) {
        return users.findById(userId).orElseThrow(() -> ApiException.notFound("user"));
    }

    public Plan planOf(Long userId) {
        return userId == null ? Plan.FREE : user(userId).getPlan();
    }

    private static OffsetDateTime startOfDay() {
        return OffsetDateTime.now(ZoneOffset.UTC).toLocalDate().atStartOfDay().atOffset(ZoneOffset.UTC);
    }

    public long countToday(Long userId, String kind) {
        return usage.countByUserIdAndKindAndCreatedAtAfter(userId, kind, startOfDay());
    }

    public UsageDto usageToday(Long userId) {
        return new UsageDto(countToday(userId, UsageEvent.ANALYSIS), countToday(userId, UsageEvent.API_CALL),
                countToday(userId, UsageEvent.EXPORT));
    }

    /** Throws plan-limit when the user's daily analysis quota is used up, otherwise records one analysis. */
    public void consumeAnalysis(Long userId, Long companyId) {
        Plan plan = planOf(userId);
        if (countToday(userId, UsageEvent.ANALYSIS) >= plan.analysesPerDay()) {
            throw ApiException.planLimit("Daily analysis limit of " + plan.analysesPerDay() + " reached on the "
                    + plan.label() + " plan.");
        }
        usage.save(new UsageEvent(userId, UsageEvent.ANALYSIS, companyId));
    }

    public void recordExport(Long userId, Long companyId) {
        usage.save(new UsageEvent(userId, UsageEvent.EXPORT, companyId));
    }
}
