package com.echo.model;

/**
 * Subscription tiers and their limits (docs/product/PRODUCT.md). Limits are enforced in the service
 * layer by {@code PlanService}; a negative value means unlimited.
 */
public enum Plan {
    FREE("Free", 0, 1, 5, 2, 365, 5, false, 0, 0),
    PRO("Pro", 29, 10, 50, 4, -1, 100, true, 2, 1_000),
    ENTERPRISE("Enterprise", 299, 100, 500, 8, -1, 2_000, true, 10, 50_000);

    private final String label;
    private final int monthlyPriceUsd;
    private final int maxWatchlists;
    private final int maxWatchlistItems;
    private final int maxCompare;
    private final int historyDays;
    private final int analysesPerDay;
    private final boolean pdfExport;
    private final int maxApiKeys;
    private final int apiCallsPerDay;

    Plan(String label, int monthlyPriceUsd, int maxWatchlists, int maxWatchlistItems, int maxCompare, int historyDays,
         int analysesPerDay, boolean pdfExport, int maxApiKeys, int apiCallsPerDay) {
        this.label = label;
        this.monthlyPriceUsd = monthlyPriceUsd;
        this.maxWatchlists = maxWatchlists;
        this.maxWatchlistItems = maxWatchlistItems;
        this.maxCompare = maxCompare;
        this.historyDays = historyDays;
        this.analysesPerDay = analysesPerDay;
        this.pdfExport = pdfExport;
        this.maxApiKeys = maxApiKeys;
        this.apiCallsPerDay = apiCallsPerDay;
    }

    public String label() { return label; }
    public int monthlyPriceUsd() { return monthlyPriceUsd; }
    public int maxWatchlists() { return maxWatchlists; }
    public int maxWatchlistItems() { return maxWatchlistItems; }
    public int maxCompare() { return maxCompare; }
    public int historyDays() { return historyDays; }
    public int analysesPerDay() { return analysesPerDay; }
    public boolean pdfExport() { return pdfExport; }
    public int maxApiKeys() { return maxApiKeys; }
    public int apiCallsPerDay() { return apiCallsPerDay; }
}
