package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.OffsetDateTime;
import java.util.Objects;

@Entity
@Table(name = "watchlist_items")
public class WatchlistItem {

    @Embeddable
    public static class Key implements Serializable {
        @Column(name = "watchlist_id")
        private Long watchlistId;

        @Column(name = "company_id")
        private Long companyId;

        protected Key() {
        }

        public Key(Long watchlistId, Long companyId) {
            this.watchlistId = watchlistId;
            this.companyId = companyId;
        }

        public Long getWatchlistId() { return watchlistId; }
        public Long getCompanyId() { return companyId; }

        @Override
        public boolean equals(Object o) {
            return o instanceof Key k && Objects.equals(watchlistId, k.watchlistId)
                    && Objects.equals(companyId, k.companyId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(watchlistId, companyId);
        }
    }

    @EmbeddedId
    private Key id;

    @Column(name = "score_drop_threshold", nullable = false)
    private short scoreDropThreshold = 10;

    @Column(name = "added_at", nullable = false)
    private OffsetDateTime addedAt = OffsetDateTime.now();

    protected WatchlistItem() {
    }

    public WatchlistItem(Key id, short scoreDropThreshold) {
        this.id = id;
        this.scoreDropThreshold = scoreDropThreshold;
    }

    public Key getId() { return id; }
    public short getScoreDropThreshold() { return scoreDropThreshold; }
    public void setScoreDropThreshold(short threshold) { this.scoreDropThreshold = threshold; }
    public OffsetDateTime getAddedAt() { return addedAt; }
}
