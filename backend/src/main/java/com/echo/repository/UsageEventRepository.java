package com.echo.repository;

import com.echo.model.UsageEvent;
import java.time.OffsetDateTime;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UsageEventRepository extends JpaRepository<UsageEvent, Long> {

    long countByUserIdAndKindAndCreatedAtAfter(Long userId, String kind, OffsetDateTime after);
}
