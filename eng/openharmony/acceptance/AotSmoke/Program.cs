var privateDirectory = args.Single();
Directory.CreateDirectory(privateDirectory);
using var certificate = ProtocolChecks.Certificate();
var builder = WebApplication.CreateSlimBuilder(new WebApplicationOptions { ContentRootPath = AppContext.BaseDirectory });
ProtocolChecks.Configure(builder, certificate);
await using var app = builder.Build();
ProtocolChecks.Map(app);
await app.StartAsync();
try { await ProtocolChecks.Run(app, certificate, privateDirectory); }
finally { await app.StopAsync(); }
Console.WriteLine("PASS AotSmoke completed; dynamic code=" + System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported);
