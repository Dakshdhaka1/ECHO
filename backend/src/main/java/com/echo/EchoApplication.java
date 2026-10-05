package com.echo;

import com.echo.config.EchoProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableConfigurationProperties(EchoProperties.class)
@EnableAsync
@EnableScheduling
@EnableCaching
public class EchoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
