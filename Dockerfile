FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY FinancialBiApp.csproj ./
RUN dotnet restore FinancialBiApp.csproj
COPY Program.cs ./
COPY wwwroot ./wwwroot
COPY financials.csv balance_sheet.csv cash_flow.csv statistics.csv ./
RUN dotnet publish FinancialBiApp.csproj -c Release -o /app/publish --no-restore /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final
RUN groupadd --system --gid 10001 appgroup \
 && useradd --system --uid 10001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=build --chown=10001:10001 /app/publish ./
ENV ASPNETCORE_URLS=http://0.0.0.0:8080 \
    DOTNET_RUNNING_IN_CONTAINER=true \
    DOTNET_EnableDiagnostics=0
EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["dotnet", "FinancialBiApp.dll"]
