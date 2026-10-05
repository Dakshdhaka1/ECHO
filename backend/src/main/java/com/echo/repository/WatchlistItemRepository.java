package com.echo.repository;

import com.echo.model.WatchlistItem;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface WatchlistItemRepository extends JpaRepository<WatchlistItem, WatchlistItem.Key> {

    List<WatchlistItem> findByIdWatchlistIdOrderByAddedAtAsc(Long watchlistId);

    long countByIdWatchlistId(Long watchlistId);

    /** (userId, threshold) pairs of everyone watching a company - used to raise alerts. */
    @Query("select w.userId, i.scoreDropThreshold from WatchlistItem i, Watchlist w "
            + "where i.id.watchlistId = w.id and i.id.companyId = :companyId")
    List<Object[]> findWatchers(Long companyId);
}
