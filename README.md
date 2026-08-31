# Capstone-Licing
# Banking-Microservices

\# Banking Microservices Platform



Plataforma de microservicios bancarios con autenticación JWT, transferencias asíncronas, y observabilidad.



\## Arquitectura



```mermaid

graph TB

&#x20;   subgraph Client

&#x20;       A\[Frontend / Mobile]

&#x20;   end



&#x20;   subgraph API Gateway

&#x20;       B\[API Gateway<br/>NestJS + Swagger]

&#x20;   end



&#x20;   subgraph Services

&#x20;       C\[Auth Service<br/>JWT + Roles]

&#x20;       D\[Accounts Service<br/>Cuentas + Transferencias]

&#x20;       E\[Transactions Service<br/>Logs + Notificaciones]

&#x20;   end



&#x20;   subgraph Infrastructure

&#x20;       F\[(PostgreSQL<br/>Cuentas)]

&#x20;       G\[(MongoDB<br/>Transacciones)]

&#x20;       H\[RabbitMQ<br/>Colas]

&#x20;       I\[Redis<br/>Caché]

&#x20;   end



&#x20;   A --> B

&#x20;   B --> C

&#x20;   B --> D

&#x20;   D --> H

&#x20;   H --> E

&#x20;   D --> F

&#x20;   E --> G

&#x20;   C --> I

```



\## Estructura del proyecto
banking-microservices/
├── apps/
│ ├── api-gateway/
│ ├── auth-service/
│ ├── accounts-service/
│ └── transactions-service/
├── libs/
│ ├── common/
│ └── rabbitmq/
├── docker/
│ └── docker-compose.yml
├── docs/
│ ├── architecture.md
│ ├── diagrams/
│ └── brainstorming/
├── .github/
│ └── workflows/
│ └── ci.yml
├── README.md
└── .env.example


## Tecnologías

- **Backend:** NestJS + TypeScript
- **Bases de datos:** PostgreSQL + MongoDB
- **Colas:** RabbitMQ
- **Caché:** Redis
- **Contenedores:** Docker + Kubernetes
- **Cloud:** AWS (ECS, Lambda, SQS)
- **Tests:** Jest + Supertest
- **CI/CD:** GitHub Actions
- **Observabilidad:** Pino + Prometheus + Grafana

## Roadmap

- [ ] Fase 1: Auth Service (JWT + Roles)
- [ ] Fase 2: Accounts Service (CRUD + Transferencias)
- [ ] Fase 3: Transactions Service + RabbitMQ
- [ ] Fase 4: API Gateway + Observabilidad
- [ ] Fase 5: Docker + Kubernetes
- [ ] Fase 6: AWS + CI/CD

## Estado actual

🚧 En desarrollo - Fase 1: Auth Service


