package com.echo.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI echoOpenApi() {
        return new OpenAPI()
                .info(new Info().title("ECHO API").version("0.1.0")
                        .description("Enterprise Corporate Health Observatory. Observable public signals and model "
                                + "estimates - not financial advice."))
                .components(new Components()
                        .addSecuritySchemes("bearer", new SecurityScheme().type(SecurityScheme.Type.HTTP)
                                .scheme("bearer").bearerFormat("JWT"))
                        .addSecuritySchemes("apiKey", new SecurityScheme().type(SecurityScheme.Type.APIKEY)
                                .in(SecurityScheme.In.HEADER).name("X-API-Key")))
                .addSecurityItem(new SecurityRequirement().addList("bearer"))
                .addSecurityItem(new SecurityRequirement().addList("apiKey"));
    }
}
