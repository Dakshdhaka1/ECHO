package com.echo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

/** Applies the Flyway migrations to a real PostgreSQL and checks the key constraints. */
@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
class SchemaMigrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void createsAllCoreTables() {
        List<String> tables = jdbc.queryForList(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
                String.class);
        assertThat(tables).contains(
                "users", "companies", "company_identifiers", "analysis_jobs", "reports",
                "score_points", "watchlists", "watchlist_items", "alerts", "api_keys", "usage_events");
    }

    @Test
    void allowsOnlyOneActiveJobPerCompanyAndDate() {
        Long companyId = jdbc.queryForObject(
                "INSERT INTO companies (market, market_id, name) VALUES ('US_SEC', '0000320193', 'Apple Inc.') "
                        + "RETURNING id",
                Long.class);
        String insertJob = "INSERT INTO analysis_jobs (company_id, as_of, status) VALUES (?, DATE '2026-10-05', ?)";

        jdbc.update(insertJob, companyId, "RUNNING");
        jdbc.update(insertJob, companyId, "DONE");

        assertThatThrownBy(() -> jdbc.update(insertJob, companyId, "QUEUED"))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
