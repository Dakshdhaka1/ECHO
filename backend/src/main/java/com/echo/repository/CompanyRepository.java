package com.echo.repository;

import com.echo.model.Company;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CompanyRepository extends JpaRepository<Company, Long> {

    Optional<Company> findByMarketAndMarketId(String market, String marketId);

    List<Company> findByDemoTrueOrderByNameAsc();

    @Query("select distinct c from Company c where c.id in "
            + "(select i.id.companyId from WatchlistItem i)")
    List<Company> findWatched();
}
