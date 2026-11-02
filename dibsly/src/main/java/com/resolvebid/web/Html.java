package com.resolvebid.web;

public final class Html {
    private Html() { }
    public static String escape(Object input) {
        if (input == null) return "";
        return input.toString().replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;");
    }
}
