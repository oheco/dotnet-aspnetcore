using Grpc.Core;
using Grpc.Net.Client;

using var certificate = ProtocolChecks.Certificate();
var builder = WebApplication.CreateBuilder();
ProtocolChecks.Configure(builder, certificate);
builder.Services.AddGrpc();
await using var app = builder.Build();
app.MapGrpcService<EchoService>();
await app.StartAsync();
try
{
    using var http = ProtocolChecks.Client(certificate);
    using var channel = GrpcChannel.ForAddress(ProtocolChecks.Address(app, "https"), new GrpcChannelOptions { HttpClient = http });
    using var call = channel.CreateCallInvoker().AsyncUnaryCall(EchoDefinition.Method, null,
        new CallOptions(deadline: DateTime.UtcNow.AddSeconds(15)), "鸿蒙 gRPC");
    ProtocolChecks.Check(await call.ResponseAsync == "鸿蒙 gRPC", "gRPC unary request over HTTPS / HTTP/2");
}
finally { await app.StopAsync(); }
Console.WriteLine("PASS GrpcSmoke completed");

// Bind explicitly so this test exercises gRPC transport without executing
// foreign protoc/Grpc.Tools binaries on the OpenHarmony host.
public class EchoService : EchoServiceBase
{
    public override Task<string> Echo(string request, ServerCallContext context) => Task.FromResult(request);
}

[BindServiceMethod(typeof(EchoDefinition), nameof(EchoDefinition.BindService))]
public abstract class EchoServiceBase
{
    public virtual Task<string> Echo(string request, ServerCallContext context) => throw new RpcException(new Status(StatusCode.Unimplemented, "unimplemented"));
}

public static class EchoDefinition
{
    public static readonly Method<string, string> Method = new(MethodType.Unary,
        "openharmony.Echo", "Echo", Marshallers.StringMarshaller, Marshallers.StringMarshaller);

    public static void BindService(ServiceBinderBase binder, EchoServiceBase? service) =>
        binder.AddMethod(Method, service is null ? null : service.Echo);
}
