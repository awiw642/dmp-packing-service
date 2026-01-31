# DMP Container Packing Service - Architecture

This document provides visual diagrams of the DMP Container Packing Service architecture, data flow, and deployment pipeline.

## System Architecture

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        WEB[Web Application]
        API_CLIENT[API Client]
    end

    subgraph Gateway["API Gateway"]
        NGINX[Nginx Reverse Proxy<br/>Port 80/443]
    end

    subgraph Application["Application Layer"]
        FASTAPI[FastAPI Application<br/>Port 8001]

        subgraph Middleware["Middleware"]
            CORS[CORS Middleware]
        end

        subgraph Endpoints["API Endpoints"]
            HEALTH[GET /health]
            PACK[POST /pack]
            VALIDATE[POST /validate]
        end

        subgraph Models["Pydantic Models"]
            REQ[PackingRequest]
            ITEM[PackingItem]
            RES[PackingResponse]
            ITEM_RES[PackingItemResult]
        end

        subgraph Algorithm["Packing Algorithm"]
            CALC[calculate_packing]
            ORIENT[find_best_orientation]
            FIT[calculate_max_fit_for_orientation]
        end

        subgraph Config["Configuration"]
            SPECS[CONTAINER_SPECS<br/>20ft / 40ft]
        end
    end

    subgraph Infrastructure["Infrastructure"]
        DOCKER[Docker Container<br/>Python 3.11]
        SYSTEMD[Systemd Service]
    end

    WEB --> NGINX
    API_CLIENT --> NGINX
    NGINX --> FASTAPI
    FASTAPI --> CORS
    CORS --> HEALTH
    CORS --> PACK
    CORS --> VALIDATE
    PACK --> REQ
    VALIDATE --> REQ
    REQ --> ITEM
    PACK --> CALC
    CALC --> ORIENT
    ORIENT --> FIT
    CALC --> SPECS
    CALC --> RES
    RES --> ITEM_RES
    FASTAPI --> DOCKER
    DOCKER --> SYSTEMD
```

## Data Flow - Packing Calculation

```mermaid
sequenceDiagram
    participant C as Client
    participant N as Nginx
    participant F as FastAPI
    participant V as Validator
    participant A as Algorithm
    participant S as Container Specs

    C->>N: POST /pack (PackingRequest)
    N->>F: Forward Request
    F->>V: Validate Request (Pydantic)

    alt Invalid Request
        V-->>F: Validation Error
        F-->>N: 422 Unprocessable Entity
        N-->>C: Error Response
    end

    V-->>F: Valid PackingRequest
    F->>S: Get Container Dimensions
    S-->>F: Container Specs (20ft/40ft)

    loop For Each Item Type
        F->>A: find_best_orientation(item, container)

        loop Try 6 Orientations
            A->>A: calculate_max_fit_for_orientation
            A->>A: Compare & Track Best
        end

        A-->>F: Best Orientation + Max Fit
        F->>F: Apply Weight Constraints
        F->>F: Calculate Fitted vs Unfitted
        F->>F: Accumulate Results
    end

    F->>F: Calculate Utilization Metrics
    F->>F: Generate Warnings (if any)
    F->>F: Build PackingResponse
    F-->>N: 200 OK (PackingResponse)
    N-->>C: JSON Response
```

## API Endpoints

```mermaid
flowchart LR
    subgraph Endpoints["API Endpoints"]
        direction TB

        subgraph Health["Health Check"]
            H_REQ["GET /health"]
            H_RES["{ status, service, version }"]
            H_REQ --> H_RES
        end

        subgraph Pack["Calculate Packing"]
            P_REQ["POST /pack"]
            P_BODY["PackingRequest<br/>- container_type<br/>- items[]"]
            P_RES["PackingResponse<br/>- success<br/>- fitted_count<br/>- items_breakdown<br/>- utilization<br/>- warnings"]
            P_REQ --> P_BODY --> P_RES
        end

        subgraph Validate["Validate Items"]
            V_REQ["POST /validate"]
            V_BODY["PackingRequest"]
            V_RES["ValidationResponse<br/>- valid<br/>- total_cbm<br/>- oversized_items<br/>- warnings"]
            V_REQ --> V_BODY --> V_RES
        end
    end
```

## Packing Algorithm Flow

```mermaid
flowchart TD
    START([Start]) --> PARSE[Parse Request]
    PARSE --> GET_CONTAINER[Get Container Specs]
    GET_CONTAINER --> INIT[Initialize Counters<br/>remaining_weight, used_volume]

    INIT --> LOOP{For Each<br/>Item Type}

    LOOP --> CHECK_SIZE{Item Fits<br/>Container?}

    CHECK_SIZE -->|No| WARN_SIZE[Add Oversized Warning]
    WARN_SIZE --> SKIP[Skip Item]
    SKIP --> NEXT

    CHECK_SIZE -->|Yes| ORIENT[Find Best Orientation]

    subgraph Orientation["Orientation Testing"]
        ORIENT --> TRY1[Try W×H×D]
        ORIENT --> TRY2[Try W×D×H]
        ORIENT --> TRY3[Try H×W×D]
        ORIENT --> TRY4[Try H×D×W]
        ORIENT --> TRY5[Try D×W×H]
        ORIENT --> TRY6[Try D×H×W]
        TRY1 & TRY2 & TRY3 & TRY4 & TRY5 & TRY6 --> BEST[Select Best<br/>Max Items]
    end

    BEST --> CALC_VOL[Calculate Max by Volume]
    CALC_VOL --> CALC_WT[Calculate Max by Weight]
    CALC_WT --> MIN_FIT[Fit = min(volume, weight, requested)]

    MIN_FIT --> UPDATE[Update Counters<br/>- remaining_weight<br/>- used_volume<br/>- fitted_count]

    UPDATE --> RESULT[Create ItemResult]
    RESULT --> NEXT{More Items?}

    NEXT -->|Yes| LOOP
    NEXT -->|No| UTIL[Calculate Utilization %]

    UTIL --> WARNINGS{Check Thresholds}
    WARNINGS -->|>95% Volume| W1[Add Volume Warning]
    WARNINGS -->|>95% Weight| W2[Add Weight Warning]
    W1 & W2 --> BUILD
    WARNINGS -->|OK| BUILD[Build PackingResponse]

    BUILD --> END([Return Response])
```

## Container Specifications

```mermaid
flowchart LR
    subgraph Containers["Container Types"]
        subgraph C20["20ft Container"]
            D20["Dimensions<br/>589 × 239 × 233 cm"]
            V20["Volume: 32.8 CBM"]
            W20["Max Weight: 25,400 kg"]
        end

        subgraph C40["40ft Container"]
            D40["Dimensions<br/>1219 × 259 × 244 cm"]
            V40["Volume: 77.0 CBM"]
            W40["Max Weight: 25,400 kg"]
        end
    end

    REQ[PackingRequest] --> |container_type| Containers
    Containers --> ALGO[Packing Algorithm]
```

## Deployment Pipeline

```mermaid
flowchart LR
    subgraph Development["Development"]
        CODE[Code Changes]
        COMMIT[Git Commit]
        PUSH[Git Push]
    end

    subgraph GitHub["GitHub"]
        REPO[Repository]
        ACTIONS[GitHub Actions]

        subgraph Workflow["Deploy Workflow"]
            TRIGGER[Push to main/master]
            SSH[SSH to VPS]
        end
    end

    subgraph VPS["Hostinger VPS"]
        GIT_PULL[git pull origin main]
        COMPOSE[docker compose up]

        subgraph Docker["Docker Environment"]
            BUILD[Build Image]
            CONTAINER[Python 3.11 Container]
            UVICORN[Uvicorn Server<br/>Port 8001]
        end

        subgraph Proxy["Reverse Proxy"]
            NGINX_CONF[Nginx Config]
            NGINX_RUN[Nginx Service]
        end
    end

    subgraph Public["Public Access"]
        ENDPOINT["/packing/*"]
    end

    CODE --> COMMIT --> PUSH
    PUSH --> REPO
    REPO --> ACTIONS
    ACTIONS --> TRIGGER
    TRIGGER --> SSH
    SSH --> GIT_PULL
    GIT_PULL --> COMPOSE
    COMPOSE --> BUILD
    BUILD --> CONTAINER
    CONTAINER --> UVICORN
    UVICORN --> NGINX_RUN
    NGINX_CONF --> NGINX_RUN
    NGINX_RUN --> ENDPOINT
```

## Request/Response Models

```mermaid
classDiagram
    class PackingItem {
        +int item_id
        +str name
        +int quantity
        +float width_cm
        +float height_cm
        +float depth_cm
        +float weight_kg
    }

    class PackingRequest {
        +str container_type
        +List~PackingItem~ items
    }

    class PackingItemResult {
        +int item_id
        +str name
        +int requested
        +int fitted
        +int unfitted
        +str dimensions_cm
        +str best_orientation
        +int items_per_layer
        +int layers
        +int max_fit_by_volume
        +int max_fit_by_weight
        +float weight_kg_total
        +float cbm_total
    }

    class PackingResponse {
        +bool success
        +str container_type
        +dict container_dimensions
        +int total_items_requested
        +int fitted_count
        +int unfitted_count
        +List~PackingItemResult~ items_breakdown
        +dict utilization
        +List~str~ warnings
    }

    PackingRequest --> PackingItem : contains
    PackingResponse --> PackingItemResult : contains
    PackingRequest ..> PackingResponse : produces
```

## Technology Stack

```mermaid
flowchart TB
    subgraph Stack["Technology Stack"]
        subgraph Runtime["Runtime Environment"]
            PY[Python 3.11]
            DOCKER[Docker]
        end

        subgraph Framework["Web Framework"]
            FASTAPI[FastAPI 0.109.0]
            UVICORN[Uvicorn 0.27.0]
            PYDANTIC[Pydantic 2.5.3]
        end

        subgraph Infrastructure["Infrastructure"]
            NGINX[Nginx]
            SYSTEMD[Systemd]
            COMPOSE[Docker Compose]
        end

        subgraph CICD["CI/CD"]
            GH_ACTIONS[GitHub Actions]
            SSH_ACTION[appleboy/ssh-action]
        end
    end

    PY --> FASTAPI
    FASTAPI --> UVICORN
    FASTAPI --> PYDANTIC
    DOCKER --> PY
    COMPOSE --> DOCKER
    SYSTEMD --> COMPOSE
    NGINX --> UVICORN
    GH_ACTIONS --> SSH_ACTION
    SSH_ACTION --> COMPOSE
```

---

*This document is automatically validated on every push to ensure diagrams remain in sync with the codebase.*
