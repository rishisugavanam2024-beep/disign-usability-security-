// Java 17+ test command with an application-owned permission check. No dependencies.
import java.util.HashSet;
import java.util.Set;

public class PermissionDemo {
    public static void main(String[] args) {
        if (args.length == 0 || !args[0].equals("read_orders")) System.exit(2);
        Set<String> permissions = new HashSet<>(Set.of("g_orders"));
        for (int i = 1; i < args.length; i++) {
            if (!args[i].equals("g_orders")) System.exit(2);
            permissions.remove(args[i]);
        }
        boolean allowed = permissions.contains("g_orders");
        // All JSON strings below are fixed; untrusted argument text is never interpolated.
        System.out.print("{\"workflow_id\":\"read_orders\",\"success\":" + allowed
            + ",\"output\":\"" + (allowed ? "orders:2" : "forbidden")
            + "\",\"message\":\"" + (allowed ? "HTTP:200" : "HTTP:403")
            + "\",\"side_effects\":{},\"validation_errors\":[],\"events\":[{"
            + "\"workflow\":\"read_orders\",\"identity\":\"alice\",\"resource\":\"orders\","
            + "\"action\":\"read\",\"allowed\":" + allowed + ",\"grant_ids\":"
            + (allowed ? "[\"g_orders\"]" : "[]") + ",\"checkpoint\":\"orders:read\"}]}");
    }
}
