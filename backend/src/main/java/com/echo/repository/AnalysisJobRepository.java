package com.echo.repository;

import com.echo.model.AnalysisJob;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface AnalysisJobRepository extends JpaRepository<AnalysisJob, UUID> {

    Optional<AnalysisJob> findFirstByCompanyIdAndAsOfAndStatusIn(Long companyId, LocalDate asOf,
                                                                  Collection<AnalysisJob.Status> statuses);

    List<AnalysisJob> findTop20ByOrderByCreatedAtDesc();

    long countByStatus(AnalysisJob.Status status);

    @Modifying
    @Query("update AnalysisJob j set j.status = com.echo.model.AnalysisJob.Status.FAILED, "
            + "j.error = 'interrupted by a backend restart', j.finishedAt = CURRENT_TIMESTAMP "
            + "where j.status in (com.echo.model.AnalysisJob.Status.QUEUED, com.echo.model.AnalysisJob.Status.RUNNING)")
    int failInterruptedJobs();
}
