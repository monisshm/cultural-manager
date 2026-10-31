import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeParseException;

public class EventManager {
    private static void fail(String message) {
        System.err.println(message);
        System.exit(2);
    }

    private static void validateEvent(String[] args) {
        if (args.length != 8) fail("Event details are incomplete.");
        String name = args[1].trim();
        String category = args[2].trim();
        String venue = args[6].trim();
        if (name.isEmpty() || category.isEmpty() || venue.isEmpty()) {
            fail("Event name, category, and venue are required.");
        }
        LocalDate eventDate;
        LocalTime start;
        LocalTime end;
        int capacity;
        try {
            eventDate = LocalDate.parse(args[3]);
            start = LocalTime.parse(args[4]);
            end = LocalTime.parse(args[5]);
            capacity = Integer.parseInt(args[7]);
        } catch (DateTimeParseException | NumberFormatException error) {
            fail("Enter a valid date, time, and whole-number registration limit.");
            return;
        }
        if (eventDate.isBefore(LocalDate.now())) fail("Event date cannot be in the past.");
        if (!end.isAfter(start)) fail("Event end time must be later than its start time.");
        if (capacity < 1 || capacity > 10000) fail("Registration limit must be between 1 and 10,000.");
        System.out.println("OK");
    }

    private static void checkRegistration(String[] args) {
        if (args.length != 4) fail("Registration details are incomplete.");
        int capacity;
        int registered;
        try {
            capacity = Integer.parseInt(args[1]);
            registered = Integer.parseInt(args[2]);
        } catch (NumberFormatException error) {
            fail("Registration capacity data is invalid.");
            return;
        }
        if ("registered".equals(args[3])) fail("You are already registered for this event.");
        if (registered >= capacity) fail("This event has reached its registration limit.");
        System.out.println("OK");
    }

    private static void validateAssignment(String[] args) {
        if (args.length != 3 || args[1].trim().isEmpty() || args[2].trim().isEmpty()) {
            fail("Event and volunteer details are required for an assignment.");
        }
        System.out.println("OK");
    }

    private static void validateCapacity(String[] args) {
        if (args.length != 3) fail("Capacity details are incomplete.");
        int capacity;
        int registered;
        try {
            capacity = Integer.parseInt(args[1]);
            registered = Integer.parseInt(args[2]);
        } catch (NumberFormatException error) {
            fail("Registration capacity data is invalid.");
            return;
        }
        if (capacity < registered) fail("Registration limit cannot be lower than current registrations.");
        System.out.println("OK");
    }

    public static void main(String[] args) {
        if (args.length == 0) fail("Choose an event-management operation.");
        switch (args[0]) {
            case "validate-event":
                validateEvent(args);
                break;
            case "can-register":
                checkRegistration(args);
                break;
            case "validate-assignment":
                validateAssignment(args);
                break;
            case "validate-capacity":
                validateCapacity(args);
                break;
            default:
                fail("Unknown event-management operation.");
        }
    }
}
