package com.echo.service;

import com.echo.dto.Dtos.CompanyDto;
import com.echo.dto.Dtos.WatchlistDto;
import com.echo.dto.Dtos.WatchlistItemDto;
import com.echo.exception.ApiException;
import com.echo.model.Company;
import com.echo.model.Plan;
import com.echo.model.Watchlist;
import com.echo.model.WatchlistItem;
import com.echo.repository.ReportRepository;
import com.echo.repository.WatchlistItemRepository;
import com.echo.repository.WatchlistRepository;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WatchlistService {

    private final WatchlistRepository watchlists;
    private final WatchlistItemRepository items;
    private final ReportRepository reports;
    private final CompanyService companies;
    private final PlanService plans;

    public WatchlistService(WatchlistRepository watchlists, WatchlistItemRepository items, ReportRepository reports,
                            CompanyService companies, PlanService plans) {
        this.watchlists = watchlists;
        this.items = items;
        this.reports = reports;
        this.companies = companies;
        this.plans = plans;
    }

    @Transactional
    public List<WatchlistDto> list(Long userId) {
        List<Watchlist> lists = watchlists.findByUserIdOrderByCreatedAtAsc(userId);
        if (lists.isEmpty()) {  // every account starts with a default watchlist
            lists = List.of(watchlists.save(new Watchlist(userId, "My watchlist")));
        }
        return lists.stream().map(this::toDto).toList();
    }

    @Transactional
    public WatchlistDto create(Long userId, String name) {
        Plan plan = plans.planOf(userId);
        if (watchlists.countByUserId(userId) >= plan.maxWatchlists()) {
            throw ApiException.planLimit("The " + plan.label() + " plan allows " + plan.maxWatchlists() + " watchlist(s).");
        }
        if (watchlists.existsByUserIdAndNameIgnoreCase(userId, name.trim())) {
            throw ApiException.conflict("You already have a watchlist with this name.");
        }
        return toDto(watchlists.save(new Watchlist(userId, name.trim())));
    }

    @Transactional
    public void delete(Long userId, Long watchlistId) {
        watchlists.delete(owned(userId, watchlistId));
    }

    @Transactional
    public WatchlistDto addItem(Long userId, Long watchlistId, Long companyId, Integer threshold) {
        Watchlist w = owned(userId, watchlistId);
        Company c = companies.get(companyId);
        Plan plan = plans.planOf(userId);
        WatchlistItem.Key key = new WatchlistItem.Key(w.getId(), c.getId());
        if (items.existsById(key)) {
            items.findById(key).ifPresent(i -> i.setScoreDropThreshold((short) (threshold == null ? 10 : threshold)));
            return toDto(w);
        }
        if (items.countByIdWatchlistId(w.getId()) >= plan.maxWatchlistItems()) {
            throw ApiException.planLimit("The " + plan.label() + " plan allows " + plan.maxWatchlistItems()
                    + " companies per watchlist.");
        }
        items.save(new WatchlistItem(key, (short) (threshold == null ? 10 : threshold)));
        return toDto(w);
    }

    @Transactional
    public WatchlistDto removeItem(Long userId, Long watchlistId, Long companyId) {
        Watchlist w = owned(userId, watchlistId);
        items.deleteById(new WatchlistItem.Key(w.getId(), companyId));
        return toDto(w);
    }

    private Watchlist owned(Long userId, Long watchlistId) {
        return watchlists.findByIdAndUserId(watchlistId, userId).orElseThrow(() -> ApiException.notFound("watchlist"));
    }

    private WatchlistDto toDto(Watchlist w) {
        List<WatchlistItemDto> list = items.findByIdWatchlistIdOrderByAddedAtAsc(w.getId()).stream().map(i -> {
            Company c = companies.get(i.getId().getCompanyId());
            var latest = reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(c.getId());
            return new WatchlistItemDto(CompanyDto.of(c), i.getScoreDropThreshold(), i.getAddedAt(),
                    latest.map(r -> r.getHealthScore()).orElse(null), latest.map(r -> r.getBand()).orElse(null),
                    latest.map(r -> r.getAsOf()).orElse(null));
        }).toList();
        return new WatchlistDto(w.getId(), w.getName(), w.getCreatedAt(), list);
    }
}
