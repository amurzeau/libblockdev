import unittest
import os
import overrides_hack

from utils import run, create_sparse_tempfile, create_lio_device, delete_lio_device, fake_utils, fake_path, TestTags, tag_test
from gi.repository import BlockDev, GLib


class DevMapperTest(unittest.TestCase):

    requested_plugins = BlockDev.plugin_specs_from_names(("dm",))

    @classmethod
    def setUpClass(cls):
        if not BlockDev.is_initialized():
            BlockDev.init(cls.requested_plugins, None)
        else:
            BlockDev.reinit(cls.requested_plugins, True, None)

class DevMapperPluginVersionCase(DevMapperTest):
    @tag_test(TestTags.NOSTORAGE)
    def test_plugin_version(self):
       self.assertEqual(BlockDev.get_plugin_soname(BlockDev.Plugin.DM), "libbd_dm.so.3")

class DevMapperTestCase(DevMapperTest):

    def setUp(self):
        self.addCleanup(self._clean_up)
        self.dev_file = create_sparse_tempfile("dm_test", 1024**3)
        try:
            self.loop_dev = create_lio_device(self.dev_file)
        except RuntimeError as e:
            raise RuntimeError("Failed to setup loop device for testing: %s" % e)

    def _clean_up(self):
        try:
            BlockDev.dm_remove("testMap")
        except:
            pass

        try:
            delete_lio_device(self.loop_dev)
        except RuntimeError:
            # just move on, we can do no better here
            pass

        os.unlink(self.dev_file)

class DevMapperGetSubsystemFromName(DevMapperTestCase):
    def _destroy_lvm(self):
        run("vgremove --yes libbd_dm_tests >/dev/null 2>&1")
        run("pvremove --yes %s >/dev/null 2>&1" % self.loop_dev)

    def _destroy_crypt(self):
        run("cryptsetup close libbd_dm_tests-subsystem_crypt >/dev/null 2>&1")

    def test_get_subsystem_from_name_lvm(self):
        """Verify that it is possible to get lvm device subsystem from its name"""
        self.addCleanup(self._destroy_lvm)
        run("vgcreate libbd_dm_tests %s >/dev/null 2>&1" % self.loop_dev)
        run("lvcreate -n subsystem_lvm -L50M libbd_dm_tests >/dev/null 2>&1")

        subsystem = BlockDev.dm_get_subsystem_from_name("libbd_dm_tests-subsystem_lvm")
        self.assertEqual(subsystem, "LVM")

    def test_get_subsystem_from_name_crypt(self):
        """Verify that it is possible to get luks device subsystem from its name"""
        self.addCleanup(self._destroy_crypt)
        run("echo \"supersecretkey\" | cryptsetup luksFormat %s -" %self.loop_dev)
        run("echo \"supersecretkey\" | cryptsetup open %s libbd_dm_tests-subsystem_crypt --key-file=-" %self.loop_dev)
        subsystem = BlockDev.dm_get_subsystem_from_name("libbd_dm_tests-subsystem_crypt")
        self.assertEqual(subsystem, "CRYPT")

class DevMapperCreateRemoveLinear(DevMapperTestCase):
    @tag_test(TestTags.CORE)
    def test_create_remove_linear(self):
        """Verify that it is possible to create new linear mapping and remove it"""

        succ = BlockDev.dm_create_linear("testMap", self.loop_dev, 100, None)
        self.assertTrue(succ)

        succ = BlockDev.dm_remove("testMap")
        self.assertTrue(succ)

class DevMapperMapExists(DevMapperTestCase):
    def test_map_exists(self):
        """Verify that testing if map exists works as expected"""

        succ = BlockDev.dm_create_linear("testMap", self.loop_dev, 100, None)
        self.assertTrue(succ)

        succ = BlockDev.dm_map_exists("testMap", True, True)
        self.assertTrue(succ)

        # suspend the map
        os.system("dmsetup suspend testMap")

        # not ignoring suspended maps, should be found
        succ = BlockDev.dm_map_exists("testMap", True, False)
        self.assertTrue(succ)

        # ignoring suspended maps, should not be found
        succ = BlockDev.dm_map_exists("testMap", True, True)
        self.assertFalse(succ)

        succ = BlockDev.dm_remove("testMap")
        self.assertTrue(succ)

        # removed, should not exist even without any restrictions
        succ = BlockDev.dm_map_exists("testMap", False, False)
        self.assertFalse(succ)

class DevMapperNameNodeBijection(DevMapperTestCase):
    def test_name_node_bijection(self):
        """Verify that the map's node and map name points to each other"""

        succ = BlockDev.dm_create_linear("testMap", self.loop_dev, 100, None)
        self.assertTrue(succ)

        self.assertEqual(BlockDev.dm_name_from_node(BlockDev.dm_node_from_name("testMap")),
                         "testMap")

        self.assertTrue(succ)

class DMDepsTest(DevMapperTest):

    @tag_test(TestTags.NOSTORAGE)
    def test_missing_dependencies(self):
        """Verify that checking for technology support works as expected"""

        with fake_utils("tests/fake_utils/dm_low_version/"):
            # too low version of dmsetup available
            with self.assertRaisesRegex(GLib.GError, "Too low version of dmsetup"):
                BlockDev.dm_is_tech_avail(BlockDev.DMTech.MAP, 0)

        with fake_path(all_but="dmsetup"):
            # no dmsetup available
            with self.assertRaisesRegex(GLib.GError, "The 'dmsetup' utility is not available"):
                BlockDev.dm_is_tech_avail(BlockDev.DMTech.MAP, 0)

    @tag_test(TestTags.NOSTORAGE)
    def test_check_dm_tech(self):
        """ Verify that BlockDev.DMTech works from Python as expected """
        self.assertTrue(hasattr(BlockDev.DMTech, "MAP"))
