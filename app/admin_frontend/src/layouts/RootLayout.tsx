import { Flex, Box, VStack, Text, IconButton, useColorMode, Spacer } from "@chakra-ui/react";
import { NavLink, Outlet } from "react-router-dom";
import { MoonIcon, SunIcon } from "@chakra-ui/icons";
import { ReactNode } from "react";

const links: Array<{ to: string; label: string }> = [
  { to: "/", label: "Дашборд" },
  { to: "/ugc", label: "UGC" },
  { to: "/scheduler", label: "Планировщик" },
  { to: "/settings", label: "Настройки" },
];

const SidebarLink = ({ to, label }: { to: string; label: string }) => (
  <NavLink
    to={to}
    end
    className={({ isActive }) => (isActive ? "link-active" : "link")}
  >
    {({ isActive }) => (
      <Box
        px={3}
        py={2}
        rounded="md"
        bg={isActive ? "gray.700" : "transparent"}
        color={isActive ? "white" : "gray.300"}
        fontWeight={isActive ? "semibold" : "medium"}
        _hover={{ bg: "gray.700", color: "white" }}
      >
        {label}
      </Box>
    )}
  </NavLink>
);

const TopBar = ({ right }: { right?: ReactNode }) => (
  <Flex
    as="header"
    align="center"
    h="64px"
    px={6}
    borderBottomWidth="1px"
    borderColor="whiteAlpha.200"
  >
    <Text fontSize="lg" fontWeight="semibold">
      Admin Console
    </Text>
    <Spacer />
    {right}
  </Flex>
);

const RootLayout = () => {
  const { colorMode, toggleColorMode } = useColorMode();

  return (
    <Flex h="100vh" bg="gray.900" color="gray.100">
      <Box
        as="nav"
        w="240px"
        borderRightWidth="1px"
        borderColor="whiteAlpha.200"
        px={4}
        py={6}
        display={{ base: "none", md: "block" }}
      >
        <VStack align="stretch" spacing={2}>
          {links.map((link) => (
            <SidebarLink key={link.to} {...link} />
          ))}
        </VStack>
      </Box>

      <Flex direction="column" flex={1} overflow="hidden">
        <TopBar
          right={
            <IconButton
              aria-label="Переключить тему"
              icon={colorMode === "light" ? <MoonIcon /> : <SunIcon />}
              onClick={toggleColorMode}
              variant="ghost"
              colorScheme="whiteAlpha"
            />
          }
        />
        <Box as="main" flex={1} overflowY="auto" p={6} bg="gray.900">
          <Outlet />
        </Box>
      </Flex>
    </Flex>
  );
};

export default RootLayout;
