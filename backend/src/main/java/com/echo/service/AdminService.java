package com.echo.service;

import com.echo.client.MlServiceClient;
import com.echo.dto.Dtos.StatsDto;
import com.echo.dto.Dtos.UserDto;
import com.echo.exception.ApiException;
import com.echo.model.AnalysisJob;
import com.echo.model.Plan;
import com.echo.model.User;
import com.echo.repository.AnalysisJobRepository;
import com.echo.repository.CompanyRepository;
import com.echo.repository.ReportRepository;
import com.echo.repository.UserRepository;
import java.util.List;
import java.util.Locale;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Service
public class AdminService {

    private final UserRepository users;
    private final CompanyRepository companies;
    private final ReportRepository reports;
    private final AnalysisJobRepository jobs;
    private final MlServiceClient ml;

    public AdminService(UserRepository users, CompanyRepository companies, ReportRepository reports,
                        AnalysisJobRepository jobs, MlServiceClient ml) {
        this.users = users;
        this.companies = companies;
        this.reports = reports;
        this.jobs = jobs;
        this.ml = ml;
    }

    @Transactional(readOnly = true)
    public List<UserDto> users() {
        return users.findAll(Sort.by("id")).stream().map(UserDto::of).toList();
    }

    @Transactional
    public UserDto updateUser(Long id, String plan, String role) {
        User u = users.findById(id).orElseThrow(() -> ApiException.notFound("user " + id));
        try {
            if (plan != null) u.changePlan(Plan.valueOf(plan.toUpperCase(Locale.ROOT)));
            if (role != null) u.setRole(User.Role.valueOf(role.toUpperCase(Locale.ROOT)));
        } catch (IllegalArgumentException e) {
            throw ApiException.badRequest("Unknown plan or role");
        }
        return UserDto.of(u);
    }

    @Transactional(readOnly = true)
    public List<JsonNode> recentJobs() {
        return jobs.findTop20ByOrderByCreatedAtDesc().stream().map(j -> (JsonNode) JsonMapper.shared().createObjectNode()
                .put("id", j.getId().toString()).put("company", j.getCompany().getName())
                .put("asOf", j.getAsOf().toString()).put("status", j.getStatus().name())
                .put("error", j.getError()).put("createdAt", j.getCreatedAt().toString())
                .put("finishedAt", j.getFinishedAt() == null ? null : j.getFinishedAt().toString())).toList();
    }

    /** Public landing-page statistics; model cards come from the ML service when it is reachable. */
    @Transactional(readOnly = true)
    public StatsDto stats() {
        JsonNode models;
        try {
            models = ml.models();
        } catch (RuntimeException e) {
            models = JsonMapper.shared().createArrayNode();
        }
        return new StatsDto(companies.count(), reports.count(), users.count(),
                jobs.countByStatus(AnalysisJob.Status.DONE), models);
    }
}
