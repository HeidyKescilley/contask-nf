# Gerador oficial do DANFSe da Receita Federal (MIT), num contêiner interno da rede "contask".
# Fonte: https://github.com/ReceitaFederal/calculadora-rtc-gerador-danfse (versão fixa abaixo).
# correcoes.patch acerta duas descrições que divergem do leiaute (NT 008, item "utilizar a descrição
# das opções previstas no leiaute"): cStat (101 é a NFS-e de substituição, não cancelada) e ambGer
# (2 é a Sefin Nacional, não homologação).
# Build: docker build -t contask-danfse deploy/danfse
FROM golang:1.27.1 AS builder
ARG COMMIT=8d79e6b2f7fad6375340afcb51c85ed370c64a14
RUN git clone -q https://github.com/ReceitaFederal/calculadora-rtc-gerador-danfse.git /src \
    && git -C /src checkout -q "$COMMIT"
WORKDIR /src
COPY correcoes.patch .
RUN git apply --verbose correcoes.patch \
    && go mod download \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /danfse-service ./cmd/danfse

FROM alpine:3.22
RUN apk add --no-cache ca-certificates tzdata
ENV TZ=America/Sao_Paulo
COPY --from=builder /danfse-service /danfse-service
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/danfse-service"]
