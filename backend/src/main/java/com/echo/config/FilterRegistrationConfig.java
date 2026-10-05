package com.echo.config;

import com.echo.security.ApiKeyAuthenticationFilter;
import com.echo.security.RequestIdFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** The security filters run inside the Spring Security chain only, not a second time as servlet filters. */
@Configuration
public class FilterRegistrationConfig {

    @Bean
    FilterRegistrationBean<ApiKeyAuthenticationFilter> apiKeyFilterRegistration(ApiKeyAuthenticationFilter filter) {
        FilterRegistrationBean<ApiKeyAuthenticationFilter> reg = new FilterRegistrationBean<>(filter);
        reg.setEnabled(false);
        return reg;
    }

    @Bean
    FilterRegistrationBean<RequestIdFilter> requestIdFilterRegistration(RequestIdFilter filter) {
        FilterRegistrationBean<RequestIdFilter> reg = new FilterRegistrationBean<>(filter);
        reg.setEnabled(false);
        return reg;
    }
}
