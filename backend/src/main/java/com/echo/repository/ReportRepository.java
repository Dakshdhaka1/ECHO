package com.echo.repository;

import com.echo.model.Report;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReportRepository extends JpaRepository<Report, Long> {

    Optional<Report> findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(Long companyId);

    Optional<Report> findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(Long companyId, LocalDate asOf);

    Optional<Report> findFirstByCompanyIdAndCaseStudyFalseAndIdLessThanOrderByIdDesc(Long companyId, Long id);

    List<Report> findTop50ByCompanyIdOrderByGeneratedAtDesc(Long companyId);
}
