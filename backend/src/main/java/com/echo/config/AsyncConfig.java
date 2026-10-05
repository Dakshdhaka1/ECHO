package com.echo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/** Bounded pool for analysis jobs: excess jobs queue instead of overloading the ML service. */
@Configuration
public class AsyncConfig {

    @Bean(name = "analysisExecutor")
    ThreadPoolTaskExecutor analysisExecutor(EchoProperties props) {
        ThreadPoolTaskExecutor ex = new ThreadPoolTaskExecutor();
        ex.setCorePoolSize(props.analysis().executorThreads());
        ex.setMaxPoolSize(props.analysis().executorThreads());
        ex.setQueueCapacity(500);
        ex.setThreadNamePrefix("analysis-");
        ex.setWaitForTasksToCompleteOnShutdown(false);
        ex.initialize();
        return ex;
    }
}
