using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;

var privateDirectory = args.Single();
Directory.CreateDirectory(privateDirectory);
using var certificate = ProtocolChecks.Certificate();
var builder = WebApplication.CreateBuilder(new WebApplicationOptions { ContentRootPath = AppContext.BaseDirectory });
ProtocolChecks.Configure(builder, certificate);
builder.Services.AddControllersWithViews();
builder.Services.AddRazorPages();
builder.Services.AddSignalR();
builder.Services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(privateDirectory, "host-keys")));
await using var app = builder.Build();
ProtocolChecks.Map(app);
app.UseStaticFiles();
app.MapControllers();
app.MapRazorPages();
app.MapHub<EchoHub>("/hub");
await app.StartAsync();
try
{
    await ProtocolChecks.Run(app, certificate, privateDirectory);
    var address = ProtocolChecks.Address(app, "http");
    using var client = ProtocolChecks.Client();
    ProtocolChecks.Check((await client.GetStringAsync(address + "/mvc")).Contains("Hello from a compiled Razor view"), "MVC and compiled Razor view");
    ProtocolChecks.Check((await client.GetStringAsync(address + "/Ready")).Contains("Razor Pages on HarmonyOS"), "Razor Pages");
    ProtocolChecks.Check((await client.GetStringAsync(address + "/probe.txt")).Trim() == "static asset on HarmonyOS", "static file content root");

    using var negotiation = await client.PostAsync(address + "/hub/negotiate?negotiateVersion=1", new StringContent(""));
    negotiation.EnsureSuccessStatusCode();
    using var negotiated = JsonDocument.Parse(await negotiation.Content.ReadAsStringAsync());
    var token = negotiated.RootElement.GetProperty("connectionToken").GetString()!;
    using var socket = new ClientWebSocket();
        socket.Options.Proxy = null; // Loopback test server belongs to this process.
    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
    await socket.ConnectAsync(new Uri(address.Replace("http:", "ws:") + "/hub?id=" + Uri.EscapeDataString(token)), timeout.Token);
    await socket.SendAsync(Encoding.UTF8.GetBytes("{\"protocol\":\"json\",\"version\":1}\u001e"), WebSocketMessageType.Text, true, timeout.Token);
    var buffer = new byte[4096];
    var received = await socket.ReceiveAsync(buffer, timeout.Token);
    ProtocolChecks.Check(Encoding.UTF8.GetString(buffer, 0, received.Count).StartsWith("{}\u001e"), "SignalR WebSocket handshake");
    await socket.SendAsync(Encoding.UTF8.GetBytes("{\"type\":1,\"invocationId\":\"1\",\"target\":\"Echo\",\"arguments\":[\"HarmonyOS\"]}\u001e"), WebSocketMessageType.Text, true, timeout.Token);
    var hubResponse = "";
    do
    {
        received = await socket.ReceiveAsync(buffer, timeout.Token);
        hubResponse += Encoding.UTF8.GetString(buffer, 0, received.Count);
    } while (!hubResponse.Contains("\"type\":3"));
    ProtocolChecks.Check(hubResponse.Contains("HarmonyOS"), "SignalR hub method invocation");
    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "done", timeout.Token);
}
finally { await app.StopAsync(); }
Console.WriteLine("PASS WebSmoke completed");

[ApiController]
public class HomeController : Controller
{
    [HttpGet("/mvc")]
    public IActionResult Index() => View();
}

public class EchoHub : Hub
{
    public string Echo(string value) => value;
}
