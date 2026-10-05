package com.echo.repository;

import com.echo.model.Watchlist;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WatchlistRepository extends JpaRepository<Watchlist, Long> {

    List<Watchlist> findByUserIdOrderByCreatedAtAsc(Long userId);

    Optional<Watchlist> findByIdAndUserId(Long id, Long userId);

    long countByUserId(Long userId);

    boolean existsByUserIdAndNameIgnoreCase(Long userId, String name);
}
