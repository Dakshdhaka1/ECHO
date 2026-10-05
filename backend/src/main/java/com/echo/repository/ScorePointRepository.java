package com.echo.repository;

import com.echo.model.ScorePoint;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScorePointRepository extends JpaRepository<ScorePoint, ScorePoint.Key> {

    List<ScorePoint> findByIdCompanyIdAndIdAsOfBetweenOrderByIdAsOfAsc(Long companyId, LocalDate from, LocalDate to);

    Optional<ScorePoint> findFirstByIdCompanyIdAndSourceAndIdAsOfLessThanOrderByIdAsOfDesc(Long companyId, String source,
                                                                                           LocalDate before);
}
