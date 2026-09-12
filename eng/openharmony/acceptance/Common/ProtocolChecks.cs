using System.IO.Compression;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.ResponseCompression;
using Microsoft.AspNetCore.Server.Kestrel.Core;

internal static class ProtocolChecks
{
    internal static readonly string LargeBody = new('x', 128 * 1024);

    internal static void Check(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("FAIL " + name);
        Console.WriteLine("PASS " + name);
    }

    internal static X509Certificate2 Certificate()
    {
        using var key = RSA.Create(2048);
        var request = new CertificateRequest("CN=localhost", key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var names = new SubjectAlternativeNameBuilder();
        names.AddDnsName("localhost");
        names.AddIpAddress(IPAddress.Loopback);
        request.CertificateExtensions.Add(names.Build());
        return request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-5), DateTimeOffset.UtcNow.AddHours(1));
    }

    internal static void Configure(WebApplicationBuilder builder, X509Certificate2 certificate)
    {
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.Listen(IPAddress.Loopback, 0, listen => listen.Protocols = HttpProtocols.Http1);
            options.Listen(IPAddress.Loopback, 0, listen =>
            {
                listen.Protocols = HttpProtocols.Http1AndHttp2;
                listen.UseHttps(certificate);
            });
        });
        builder.Services.AddResponseCompression(options => options.Providers.Add<GzipCompressionProvider>());
        builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.TypeInfoResolverChain.Insert(0, SmokeJsonContext.Default));
    }

    internal static void Map(WebApplication app)
    {
        app.UseExceptionHandler(handler => handler.Run(async context =>
        {
            context.Response.StatusCode = 500;
            await context.Response.WriteAsync("handled");
        }));
        app.UseResponseCompression();
        app.UseWebSockets();
        app.MapGet("/health", () => "healthy");
        app.MapGet("/json", () => new SmokePayload("HarmonyOS", 10));
        app.MapPost("/echo", async (HttpRequest request) =>
        {
            using var reader = new StreamReader(request.Body);
            return await reader.ReadToEndAsync();
        });
        app.MapPost("/buffer", async (HttpRequest request) =>
        {
            request.EnableBuffering(bufferThreshold: 16, bufferLimit: 1024 * 1024);
            using var first = new MemoryStream();
            await request.Body.CopyToAsync(first);
            request.Body.Position = 0;
            using var second = new MemoryStream();
            await request.Body.CopyToAsync(second);
            return first.ToArray().AsSpan().SequenceEqual(second.ToArray()) ? "buffered" : "mismatch";
        });
        app.MapGet("/large", () => Results.Text(LargeBody));
        app.MapGet("/fail", (HttpContext _) => { throw new InvalidOperationException("acceptance-only exception"); });
        app.MapGet("/slow", async (HttpContext context) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(30), context.RequestAborted);
            return "finished";
        });
        app.Map("/ws", async context =>
        {
            if (!context.WebSockets.IsWebSocketRequest)
            {
                context.Response.StatusCode = 400;
                return;
            }
            using var socket = await context.WebSockets.AcceptWebSocketAsync();
            var buffer = new byte[8192];
            while (socket.State == WebSocketState.Open)
            {
                var received = await socket.ReceiveAsync(buffer, context.RequestAborted);
                if (received.MessageType == WebSocketMessageType.Close)
                {
                    await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "done", CancellationToken.None);
                    break;
                }
                await socket.SendAsync(buffer.AsMemory(0, received.Count), received.MessageType, received.EndOfMessage, context.RequestAborted);
            }
        });
    }

    internal static string Address(WebApplication app, string scheme) =>
        app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single(a => a.StartsWith(scheme + "://", StringComparison.Ordinal));

    internal static HttpClient Client(X509Certificate2? certificate = null)
    {
        var handler = new SocketsHttpHandler { UseProxy = false };
        if (certificate is not null)
        {
            // Trust only this test's ephemeral certificate; system trust is unchanged.
            var fingerprint = certificate.GetCertHashString(HashAlgorithmName.SHA256);
            handler.SslOptions.RemoteCertificateValidationCallback = (_, peer, _, errors) =>
                peer is not null && (errors & SslPolicyErrors.RemoteCertificateNameMismatch) == 0 &&
                peer.GetCertHashString(HashAlgorithmName.SHA256) == fingerprint;
        }
        return new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };
    }

    internal static async Task Run(WebApplication app, X509Certificate2 certificate, string privateDirectory)
    {
        var http = Address(app, "http");
        var https = Address(app, "https");
        using var client = Client();
        Check(await client.GetStringAsync(http + "/health") == "healthy", "HTTP/1.1 request");
        var json = await client.GetStringAsync(http + "/json");
        Check(json.Contains("HarmonyOS") && json.Contains("10"), "JSON source generation");
        using var echoed = await client.PostAsync(http + "/echo", new StringContent("鸿蒙 ASP.NET Core"));
        Check(await echoed.Content.ReadAsStringAsync() == "鸿蒙 ASP.NET Core", "UTF-8 POST");
        using var buffered = await client.PostAsync(http + "/buffer", new StringContent(LargeBody));
        Check(await buffered.Content.ReadAsStringAsync() == "buffered", "request body spills to private temporary file and rewinds");
        Check(!Directory.EnumerateFiles(Path.GetTempPath(), "ASPNETCORE_*.tmp").Any(), "request temporary file cleanup");

        using var tlsClient = Client(certificate);
        using var h2Request = new HttpRequestMessage(HttpMethod.Get, https + "/health")
        {
            Version = HttpVersion.Version20,
            VersionPolicy = HttpVersionPolicy.RequestVersionExact
        };
        using var h2Response = await tlsClient.SendAsync(h2Request);
        Check(h2Response.IsSuccessStatusCode && h2Response.Version.Major == 2 && await h2Response.Content.ReadAsStringAsync() == "healthy", "HTTPS / HTTP/2 with ALPN and pinned test certificate");

        using var compressedRequest = new HttpRequestMessage(HttpMethod.Get, http + "/large");
        compressedRequest.Headers.AcceptEncoding.ParseAdd("gzip");
        using var compressed = await client.SendAsync(compressedRequest);
        using var gzip = new GZipStream(await compressed.Content.ReadAsStreamAsync(), CompressionMode.Decompress);
        using var reader = new StreamReader(gzip);
        Check(compressed.Content.Headers.ContentEncoding.Contains("gzip") && await reader.ReadToEndAsync() == LargeBody, "gzip response compression");

        using var ws = new ClientWebSocket();
        ws.Options.Proxy = null; // Loopback test server belongs to this process.
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        await ws.ConnectAsync(new Uri(http.Replace("http:", "ws:") + "/ws"), timeout.Token);
        var payload = Encoding.UTF8.GetBytes("websocket 鸿蒙");
        await ws.SendAsync(payload.AsMemory(0, 4), WebSocketMessageType.Text, false, timeout.Token);
        await ws.SendAsync(payload.AsMemory(4), WebSocketMessageType.Text, true, timeout.Token);
        using var message = new MemoryStream();
        var data = new byte[128];
        ValueWebSocketReceiveResult received;
        do
        {
            received = await ws.ReceiveAsync(data.AsMemory(), timeout.Token);
            message.Write(data, 0, received.Count);
        } while (!received.EndOfMessage);
        Check(message.ToArray().AsSpan().SequenceEqual(payload), "WebSocket fragmented UTF-8 message");
        await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "done", timeout.Token);

        using var missing = await client.GetAsync(http + "/missing");
        using var wrongMethod = await client.GetAsync(http + "/echo");
        using var failure = await client.GetAsync(http + "/fail");
        Check(missing.StatusCode == HttpStatusCode.NotFound && wrongMethod.StatusCode == HttpStatusCode.MethodNotAllowed && failure.StatusCode == HttpStatusCode.InternalServerError && await failure.Content.ReadAsStringAsync() == "handled", "404, 405 and handled 500 responses");

        var replies = await Task.WhenAll(Enumerable.Range(0, 32).Select(_ => client.GetStringAsync(http + "/health")));
        Check(replies.All(value => value == "healthy"), "32 concurrent requests");
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(200));
        try
        {
            await client.GetAsync(http + "/slow", cancellation.Token);
            throw new InvalidOperationException("Request was not cancelled");
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        Check(await client.GetStringAsync(http + "/health") == "healthy", "cancelled request leaves server healthy");

        using var badClient = new TcpClient();
        var endpoint = new Uri(http);
        await badClient.ConnectAsync(endpoint.Host, endpoint.Port, timeout.Token);
        await badClient.GetStream().WriteAsync("invalid request\r\n\r\n"u8.ToArray(), timeout.Token);
        var response = new byte[1024];
        var count = await badClient.GetStream().ReadAsync(response, timeout.Token);
        Check(Encoding.ASCII.GetString(response, 0, count).StartsWith("HTTP/1.1 400", StringComparison.Ordinal), "malformed HTTP request rejection");

        var keys = new DirectoryInfo(Path.Combine(privateDirectory, "keys"));
        var provider = DataProtectionProvider.Create(keys);
        var protectedValue = provider.CreateProtector("acceptance").Protect("persisted secret");
        var secondProvider = DataProtectionProvider.Create(keys);
        Check(secondProvider.CreateProtector("acceptance").Unprotect(protectedValue) == "persisted secret" && keys.GetFiles("*.xml").Length > 0, "Data Protection key persistence and reload");
        if (OperatingSystem.IsLinux() || OperatingSystem.IsWindows() || OperatingSystem.IsMacOS())
            Console.WriteLine("INFO QUIC supported=" + System.Net.Quic.QuicListener.IsSupported);
    }
}

internal record SmokePayload(string Platform, int Version);

[JsonSerializable(typeof(SmokePayload))]
internal partial class SmokeJsonContext : JsonSerializerContext;
