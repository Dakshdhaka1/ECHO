package com.echo.service;

import com.echo.client.MlServiceClient;
import com.echo.dto.Dtos.CompanyDto;
import com.echo.dto.Dtos.SearchResultDto;
import com.echo.exception.ApiException;
import com.echo.model.Company;
import com.echo.repository.CompanyRepository;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/** Company registry: search via the ML service's resolver, upserting every candidate so it gets a stable id. */
@Service
public class CompanyService {

    private final CompanyRepository companies;
    private final MlServiceClient ml;

    public CompanyService(CompanyRepository companies, MlServiceClient ml) {
        this.companies = companies;
        this.ml = ml;
    }

    @Transactional
    public List<SearchResultDto> search(String query) {
        String q = query == null ? "" : query.trim();
        if (q.length() < 2) {
            throw ApiException.badRequest("Search needs at least 2 characters.");
        }
        List<SearchResultDto> out = new ArrayList<>();
        for (JsonNode c : ml.resolve(q, 8)) {
            Company company = upsert(c.path("market").asString(), c.path("market_id").asString(),
                    c.path("name").asString(), c.path("ticker").isNull() ? null : c.path("ticker").asString(),
                    c.path("is_demo").asBoolean(false));
            List<String> former = new ArrayList<>();
            c.path("former_names").forEach(n -> former.add(n.asString()));
            out.add(new SearchResultDto(CompanyDto.of(company), c.path("match_score").asDouble(), former));
        }
        return out;
    }

    @Transactional
    public Company upsert(String market, String marketId, String name, String ticker, Boolean demo) {
        Company c = companies.findByMarketAndMarketId(market, marketId)
                .orElseGet(() -> companies.save(new Company(market, marketId, name)));
        c.updateIdentity(name, ticker, demo);
        return companies.save(c);
    }

    @Transactional(readOnly = true)
    public Company get(Long id) {
        return companies.findById(id).orElseThrow(() -> ApiException.notFound("company " + id));
    }

    /** Demo universe (with historical case-study dates), registered so the landing page can link straight in. */
    @Transactional
    public List<JsonNode> universe() {
        List<JsonNode> out = new ArrayList<>();
        for (JsonNode u : ml.universe()) {
            Company c = upsert(u.path("market").asString(), u.path("market_id").asString(), u.path("name").asString(),
                    u.path("ticker").asString(null), true);
            out.add(tools.jackson.databind.json.JsonMapper.shared().createObjectNode()
                    .put("companyId", c.getId())
                    .put("name", c.getName())
                    .put("ticker", c.getTicker())
                    .put("role", u.path("role").asString())
                    .put("caseStudy", u.path("case_study").asString(null))
                    .set("asOf", u.path("as_of")));
        }
        return out;
    }
}
