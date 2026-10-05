package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

/** Market-agnostic company registry; {@code marketId} is the CIK for US_SEC. */
@Entity
@Table(name = "companies")
public class Company {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String market;

    @Column(name = "market_id", nullable = false)
    private String marketId;

    @Column(nullable = false)
    private String name;

    private String ticker;
    private String exchange;
    @Column(columnDefinition = "bpchar(2)")
    private String country;

    @Column(name = "industry_scheme")
    private String industryScheme;

    @Column(name = "industry_code")
    private String industryCode;

    private String sector;

    @Column(nullable = false)
    private String status = "ACTIVE";

    @Column(name = "is_demo", nullable = false)
    private boolean demo;

    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt = OffsetDateTime.now();

    protected Company() {
    }

    public Company(String market, String marketId, String name) {
        this.market = market;
        this.marketId = marketId;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getMarket() { return market; }
    public String getMarketId() { return marketId; }
    public String getName() { return name; }
    public String getTicker() { return ticker; }
    public String getExchange() { return exchange; }
    public String getSector() { return sector; }
    public String getIndustryCode() { return industryCode; }
    public String getStatus() { return status; }
    public boolean isDemo() { return demo; }

    public void updateIdentity(String newName, String newTicker, Boolean isDemo) {
        if (newName != null && !newName.isBlank()) this.name = newName;
        if (newTicker != null && !newTicker.isBlank()) this.ticker = newTicker;
        if (isDemo != null) this.demo = isDemo;
        this.updatedAt = OffsetDateTime.now();
    }

    public void updateProfile(String newSector, String sic, String newExchange) {
        if (newSector != null) this.sector = newSector;
        if (sic != null) {
            this.industryScheme = "SIC";
            this.industryCode = sic;
        }
        if (newExchange != null) this.exchange = newExchange;
        this.country = "US";
        this.updatedAt = OffsetDateTime.now();
    }
}
